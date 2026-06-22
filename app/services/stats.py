import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.enums import SENSITIVE_CATEGORIES, UtilityType
from app.models.bill import Bill
from app.models.document import Document
from app.models.expense import Expense
from app.models.user import User
from app.services import bills as bills_service
from app.services import categories as categories_service

_SENSITIVE = list(SENSITIVE_CATEGORIES)

# Categorie con cui le bollette/spese di casa compaiono nelle viste aggregate
# della dashboard, così da contare *tutte* le spese senza confonderle con le
# categorie merceologiche degli scontrini. Le spese di CONDOMINIO sono tenute
# distinte dalle bollette delle utenze: hanno natura diversa e vanno mostrate
# come categoria a sé.
BILLS_CATEGORY_UTILITIES = "Bollette / utenze"
BILLS_CATEGORY_CONDO = "Spese condominiali"
# Le bollette sono spese del nucleo: nelle ripartizioni per ambito le
# attribuiamo all'ambito familiare.
BILLS_SCOPE = "familiare"


async def by_category(db: AsyncSession, household_id: uuid.UUID, year: int | None = None):
    """Spesa per categoria, organizzata in DUE LIVELLI per coerenza: le voci di
    reparto del supermercato sono raccolte nella macro-categoria «spesa
    supermercato» (con il dettaglio in `subcategories`); le altre categorie (es.
    farmaci, personalizzate) restano di primo livello. Le bollette compaiono come
    macro-categorie a sé (utenze e spese condominiali). Ogni riga ha sempre il
    campo `subcategories` (lista, vuota per le foglie)."""
    stmt = (
        select(Expense.merch_category, func.sum(Expense.line_amount), func.count())
        .where(Expense.household_id == household_id)
        .group_by(Expense.merch_category)
    )
    if year:
        stmt = stmt.where(Expense.fiscal_year == year)
    res = await db.execute(stmt)

    leaf_group = await categories_service.leaf_to_group(db, household_id)
    # Aggrega le foglie nelle rispettive macro-categorie (gruppi).
    groups: dict[str, dict] = {}
    for cat, total, count in res.all():
        leaf = cat or "n/d"
        group = leaf_group.get(leaf, leaf)
        t, n = round(float(total or 0), 2), int(count or 0)
        g = groups.setdefault(group, {"category": group, "total": 0.0, "count": 0, "subs": {}})
        g["total"] = round(g["total"] + t, 2)
        g["count"] += n
        # Tieni il dettaglio per reparto solo quando la foglia è davvero una
        # sottocategoria (gruppo diverso dal proprio nome).
        if group != leaf:
            sub = g["subs"].setdefault(leaf, {"category": leaf, "total": 0.0, "count": 0})
            sub["total"] = round(sub["total"] + t, 2)
            sub["count"] += n

    rows = []
    for g in groups.values():
        subs = sorted(g["subs"].values(), key=lambda r: r["total"], reverse=True)
        rows.append(
            {"category": g["category"], "total": g["total"], "count": g["count"],
             "subcategories": subs}
        )

    # Aggiunge le bollette per tenere conto di tutte le spese, distinguendo le
    # utenze (luce, gas, acqua, ...) dalle spese condominiali.
    util_t, util_c, condo_t, condo_c = await _bills_split_total(db, household_id, year)
    if util_c:
        rows.append({"category": BILLS_CATEGORY_UTILITIES, "total": round(util_t, 2), "count": util_c, "subcategories": []})
    if condo_c:
        rows.append({"category": BILLS_CATEGORY_CONDO, "total": round(condo_t, 2), "count": condo_c, "subcategories": []})

    rows.sort(key=lambda r: r["total"], reverse=True)
    return rows


async def by_member(db: AsyncSession, household_id: uuid.UUID, year: int | None = None):
    totals: dict[str, list] = {}

    estmt = (
        select(User.full_name, func.sum(Expense.line_amount), func.count())
        .join(Expense, Expense.payer_user_id == User.id)
        .where(Expense.household_id == household_id)
        .group_by(User.full_name)
    )
    if year:
        estmt = estmt.where(Expense.fiscal_year == year)
    for m, t, n in (await db.execute(estmt)).all():
        totals[m] = [float(t or 0), int(n or 0)]

    # Anche le bollette concorrono alla spesa del soggetto pagante (intestatario).
    bstmt = (
        select(User.full_name, func.sum(Bill.total_amount), func.count())
        .join(Bill, Bill.payer_user_id == User.id)
        .where(Bill.household_id == household_id)
        .group_by(User.full_name)
    )
    if year:
        bstmt = bstmt.where(Bill.fiscal_year == year)
    for m, t, n in (await db.execute(bstmt)).all():
        row = totals.setdefault(m, [0.0, 0])
        row[0] += float(t or 0)
        row[1] += int(n or 0)

    out = [
        {"member": m, "total": round(t, 2), "count": n}
        for m, (t, n) in totals.items()
    ]
    out.sort(key=lambda r: r["total"], reverse=True)
    return out


async def by_scope(db: AsyncSession, household_id: uuid.UUID, year: int | None = None):
    stmt = (
        select(Expense.scope, func.sum(Expense.line_amount), func.count())
        .where(Expense.household_id == household_id)
        .group_by(Expense.scope)
    )
    if year:
        stmt = stmt.where(Expense.fiscal_year == year)
    res = await db.execute(stmt)
    totals: dict[str, list] = {
        str(s): [float(t or 0), int(n or 0)] for s, t, n in res.all()
    }

    # Le bollette sono spese del nucleo: le sommiamo all'ambito familiare.
    btotal, bcount = await _bills_total(db, household_id, year)
    if bcount:
        row = totals.setdefault(BILLS_SCOPE, [0.0, 0])
        row[0] += btotal
        row[1] += bcount

    return [
        {"scope": s, "total": round(t, 2), "count": n}
        for s, (t, n) in totals.items()
    ]


async def yearly(db: AsyncSession, household_id: uuid.UUID):
    totals: dict[int, list] = {}

    estmt = (
        select(Expense.fiscal_year, func.sum(Expense.line_amount), func.count())
        .where(Expense.household_id == household_id)
        .group_by(Expense.fiscal_year)
    )
    for y, t, n in (await db.execute(estmt)).all():
        totals[y] = [float(t or 0), int(n or 0)]

    bstmt = (
        select(Bill.fiscal_year, func.sum(Bill.total_amount), func.count())
        .where(Bill.household_id == household_id)
        .group_by(Bill.fiscal_year)
    )
    for y, t, n in (await db.execute(bstmt)).all():
        row = totals.setdefault(y, [0.0, 0])
        row[0] += float(t or 0)
        row[1] += int(n or 0)

    return [
        {"year": y, "total": round(t, 2), "count": n}
        for y, (t, n) in sorted(totals.items(), key=lambda kv: (kv[0] is None, kv[0]))
    ]


async def _bills_total(
    db: AsyncSession, household_id: uuid.UUID, year: int | None = None
) -> tuple[float, int]:
    """Totale e numero delle bollette/spese di casa del nucleo."""
    stmt = select(
        func.coalesce(func.sum(Bill.total_amount), 0), func.count(Bill.id)
    ).where(Bill.household_id == household_id)
    if year:
        stmt = stmt.where(Bill.fiscal_year == year)
    total, count = (await db.execute(stmt)).one()
    return float(total or 0), int(count or 0)


async def _bills_split_total(
    db: AsyncSession, household_id: uuid.UUID, year: int | None = None
) -> tuple[float, int, float, int]:
    """Totale/numero delle bollette diviso tra utenze e condominio:
    (utenze_totale, utenze_n, condominio_totale, condominio_n)."""
    stmt = (
        select(
            Bill.utility_type,
            func.coalesce(func.sum(Bill.total_amount), 0),
            func.count(Bill.id),
        )
        .where(Bill.household_id == household_id)
        .group_by(Bill.utility_type)
    )
    if year:
        stmt = stmt.where(Bill.fiscal_year == year)
    util_t, util_c, condo_t, condo_c = 0.0, 0, 0.0, 0
    for utype, total, count in (await db.execute(stmt)).all():
        if utype == UtilityType.CONDOMINIO:
            condo_t += float(total or 0)
            condo_c += int(count or 0)
        else:
            util_t += float(total or 0)
            util_c += int(count or 0)
    return util_t, util_c, condo_t, condo_c


async def fiscal_summary(
    db: AsyncSession, household_id: uuid.UUID, year: int | None = None
):
    stmt = (
        select(Expense.fiscal_classification, func.sum(Expense.line_amount), func.count())
        .where(Expense.household_id == household_id)
        .group_by(Expense.fiscal_classification)
    )
    if year:
        stmt = stmt.where(Expense.fiscal_year == year)
    res = await db.execute(stmt)
    return [
        {"classification": str(c), "total": float(t or 0), "count": n}
        for c, t, n in res.all()
    ]


async def overview(db: AsyncSession, household_id: uuid.UUID, year: int | None = None):
    """KPI sintetici per la dashboard: totale speso (spese + bollette), n.
    movimenti, n. bollette, n. documenti, documenti da rivedere e totale
    potenzialmente agevolabile."""
    exp = select(
        func.coalesce(func.sum(Expense.line_amount), 0),
        func.count(Expense.id),
    ).where(Expense.household_id == household_id)
    if year:
        exp = exp.where(Expense.fiscal_year == year)
    expenses_total, lines = (await db.execute(exp)).one()

    # Le bollette/spese di casa sono archiviate a parte: le includiamo qui per
    # avere il totale di *tutte* le spese del nucleo nella dashboard.
    bills_total, bills_count = await _bills_total(db, household_id, year)

    ded = select(func.coalesce(func.sum(Expense.line_amount), 0)).where(
        Expense.household_id == household_id,
        Expense.fiscal_classification.in_(["detraibile", "deducibile"]),
    )
    if year:
        ded = ded.where(Expense.fiscal_year == year)
    deductible = (await db.execute(ded)).scalar_one()

    docs = select(func.count(Document.id)).where(Document.household_id == household_id)
    review = select(func.count(Document.id)).where(
        Document.household_id == household_id,
        Document.status.in_(["needs_review", "pending", "processing"]),
    )
    if year:
        docs = docs.where(Document.fiscal_year == year)
    docs_count = (await db.execute(docs)).scalar_one()
    review_count = (await db.execute(review)).scalar_one()

    expenses_total = float(expenses_total or 0)
    return {
        "total": round(expenses_total + bills_total, 2),
        "expenses_total": round(expenses_total, 2),
        "bills_total": round(bills_total, 2),
        "lines": int(lines or 0),
        "bills": int(bills_count or 0),
        "documents": int(docs_count or 0),
        "to_review": int(review_count or 0),
        "deductible_total": float(deductible or 0),
    }


async def fiscal_by_member(db: AsyncSession, household_id: uuid.UUID, year: int | None = None):
    """Per l'export al commercialista: per ogni soggetto pagante e per ogni
    classificazione fiscale, totale e numero movimenti."""
    payer = aliased(User)
    stmt = (
        select(
            payer.full_name,
            payer.codice_fiscale,
            Expense.fiscal_classification,
            func.sum(Expense.line_amount),
            func.count(Expense.id),
        )
        .join(payer, Expense.payer_user_id == payer.id, isouter=True)
        .where(Expense.household_id == household_id)
        .group_by(payer.full_name, payer.codice_fiscale, Expense.fiscal_classification)
        .order_by(payer.full_name, Expense.fiscal_classification)
    )
    if year:
        stmt = stmt.where(Expense.fiscal_year == year)
    res = await db.execute(stmt)
    return [
        {
            "member": name or "Non attribuito",
            "codice_fiscale": cf or "",
            "classification": str(c),
            "total": float(t or 0),
            "count": n,
        }
        for name, cf, c, t, n in res.all()
    ]


# ---------------------------------------------------------------------------
# Analisi avanzate: andamento mensile, esercenti più frequenti, confronto tra
# anni e "insight" automatici. Pensate per arricchire la dashboard e dare al
# nucleo una lettura più completa delle proprie spese (oltre ai totali).
# ---------------------------------------------------------------------------

# Etichette dei mesi (italiano) per le viste/export, indicizzate 1..12.
MONTH_LABELS: list[str] = [
    "", "Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
    "Lug", "Ago", "Set", "Ott", "Nov", "Dic",
]


def _pct_change(current: float, previous: float) -> float | None:
    """Variazione percentuale current vs previous (None se base nulla)."""
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


async def monthly(db: AsyncSession, household_id: uuid.UUID, year: int):
    """Andamento mensile (gennaio→dicembre) dell'anno indicato: spese e bollette
    per mese, così da leggere la stagionalità e i picchi di spesa del nucleo."""
    months: dict[int, dict] = {
        m: {"expenses_total": 0.0, "bills_total": 0.0, "count": 0} for m in range(1, 13)
    }

    emonth = func.extract("month", Expense.purchase_date)
    estmt = (
        select(emonth, func.coalesce(func.sum(Expense.line_amount), 0), func.count())
        .where(
            Expense.household_id == household_id,
            Expense.fiscal_year == year,
            Expense.purchase_date.is_not(None),
        )
        .group_by(emonth)
    )
    for m, t, n in (await db.execute(estmt)).all():
        if m is None:
            continue
        row = months[int(m)]
        row["expenses_total"] = float(t or 0)
        row["count"] += int(n or 0)

    # Le bollette non hanno purchase_date: usiamo la data di competenza più
    # significativa disponibile (fine periodo → emissione → scadenza → inizio).
    ref = func.coalesce(
        Bill.period_end, Bill.issue_date, Bill.due_date, Bill.period_start
    )
    bmonth = func.extract("month", ref)
    bstmt = (
        select(bmonth, func.coalesce(func.sum(Bill.total_amount), 0), func.count())
        .where(Bill.household_id == household_id, Bill.fiscal_year == year)
        .group_by(bmonth)
    )
    for m, t, n in (await db.execute(bstmt)).all():
        if m is None:
            continue
        row = months[int(m)]
        row["bills_total"] = float(t or 0)
        row["count"] += int(n or 0)

    return [
        {
            "month": m,
            "label": MONTH_LABELS[m],
            "expenses_total": round(months[m]["expenses_total"], 2),
            "bills_total": round(months[m]["bills_total"], 2),
            "total": round(months[m]["expenses_total"] + months[m]["bills_total"], 2),
            "count": months[m]["count"],
        }
        for m in range(1, 13)
    ]


async def top_merchants(
    db: AsyncSession,
    household_id: uuid.UUID,
    year: int | None = None,
    limit: int = 10,
    is_admin: bool = True,
):
    """Esercenti/fornitori su cui il nucleo spende di più (per importo totale).
    Per i non-amministratori esclude le righe della categoria sensibile farmaci."""
    stmt = (
        select(
            Expense.merchant,
            func.sum(Expense.line_amount),
            func.count(),
            func.max(Expense.purchase_date),
        )
        .where(
            Expense.household_id == household_id,
            Expense.merchant.is_not(None),
            Expense.merchant != "",
        )
        .group_by(Expense.merchant)
        .order_by(func.sum(Expense.line_amount).desc())
        .limit(limit)
    )
    if year:
        stmt = stmt.where(Expense.fiscal_year == year)
    if not is_admin:
        stmt = stmt.where(
            Expense.merch_category.notin_(_SENSITIVE)
            | Expense.merch_category.is_(None)
        )
    res = await db.execute(stmt)
    return [
        {
            "merchant": m,
            "total": round(float(t or 0), 2),
            "count": int(n or 0),
            "last_purchase": d.isoformat() if d else None,
        }
        for m, t, n, d in res.all()
    ]


async def compare_years(
    db: AsyncSession,
    household_id: uuid.UUID,
    year: int,
    is_admin: bool = True,
):
    """Confronto dell'anno indicato con il precedente: totali e variazione per
    categoria, per cogliere subito rincari e voci in crescita/calo."""
    prev = year - 1
    cur_rows = await by_category(db, household_id, year)
    prev_rows = await by_category(db, household_id, prev)
    if not is_admin:
        cur_rows = [r for r in cur_rows if r["category"] not in SENSITIVE_CATEGORIES]
        prev_rows = [r for r in prev_rows if r["category"] not in SENSITIVE_CATEGORIES]

    cur_map = {r["category"]: r["total"] for r in cur_rows}
    prev_map = {r["category"]: r["total"] for r in prev_rows}
    categories = set(cur_map) | set(prev_map)
    by_cat = []
    for cat in categories:
        ct = cur_map.get(cat, 0.0)
        pt = prev_map.get(cat, 0.0)
        by_cat.append(
            {
                "category": cat,
                "current": round(ct, 2),
                "previous": round(pt, 2),
                "delta": round(ct - pt, 2),
                "delta_pct": _pct_change(ct, pt),
            }
        )
    by_cat.sort(key=lambda r: r["current"], reverse=True)

    cur_total = round(sum(cur_map.values()), 2)
    prev_total = round(sum(prev_map.values()), 2)
    return {
        "year": year,
        "previous_year": prev,
        "current_total": cur_total,
        "previous_total": prev_total,
        "delta": round(cur_total - prev_total, 2),
        "delta_pct": _pct_change(cur_total, prev_total),
        "by_category": by_cat,
    }


def _compute_insights(
    year: int,
    overview_data: dict,
    comparison: dict,
    categories: list[dict],
    fiscal: list[dict],
    upcoming_bills: dict,
) -> list[dict]:
    """Costruisce gli "insight" (osservazioni automatiche) a partire dai dati
    già aggregati. Funzione pura: nessun accesso al DB, così è testabile a parte.
    Ogni insight ha `severity` (positive/info/warning), un'icona, un titolo e un
    dettaglio leggibile."""
    out: list[dict] = []

    # 1) Variazione complessiva rispetto all'anno precedente.
    dpct = comparison.get("delta_pct")
    if dpct is not None and comparison.get("previous_total"):
        if dpct > 5:
            out.append({
                "severity": "warning",
                "icon": "📈",
                "title": f"Spesa in aumento del {dpct:.1f}% sul {comparison['previous_year']}",
                "detail": f"Nel {year} hai speso {comparison['current_total']:.2f} € contro {comparison['previous_total']:.2f} € dell'anno prima.",
            })
        elif dpct < -5:
            out.append({
                "severity": "positive",
                "icon": "📉",
                "title": f"Spesa in calo del {abs(dpct):.1f}% sul {comparison['previous_year']}",
                "detail": f"Nel {year} hai speso {comparison['current_total']:.2f} € contro {comparison['previous_total']:.2f} € dell'anno prima.",
            })
        else:
            out.append({
                "severity": "info",
                "icon": "➖",
                "title": "Spesa stabile rispetto all'anno precedente",
                "detail": f"Variazione del {dpct:.1f}% sul {comparison['previous_year']}.",
            })

    # 2) Categoria con il maggior aumento in valore assoluto.
    growers = [
        c for c in comparison.get("by_category", [])
        if c["delta"] > 0 and c["previous"] > 0
    ]
    if growers:
        top = max(growers, key=lambda c: c["delta"])
        pct = f" (+{top['delta_pct']:.1f}%)" if top.get("delta_pct") is not None else ""
        out.append({
            "severity": "warning",
            "icon": "🔺",
            "title": f"«{top['category']}» è la voce cresciuta di più",
            "detail": f"+{top['delta']:.2f} €{pct} rispetto al {comparison['previous_year']}.",
        })

    # 3) Categoria di spesa principale dell'anno.
    spendable = [c for c in categories if c.get("total", 0) > 0]
    if spendable:
        top_cat = max(spendable, key=lambda c: c["total"])
        total_all = sum(c["total"] for c in spendable) or 1
        share = top_cat["total"] / total_all * 100
        out.append({
            "severity": "info",
            "icon": "🏆",
            "title": f"Voce principale: «{top_cat['category']}»",
            "detail": f"{top_cat['total']:.2f} € ({share:.0f}% del totale, {top_cat['count']} moviment{'o' if top_cat['count'] == 1 else 'i'}).",
        })

    # 4) Potenziale fiscale (detraibile/deducibile) + voci da verificare.
    ded = overview_data.get("deductible_total", 0)
    if ded:
        out.append({
            "severity": "positive",
            "icon": "🏷️",
            "title": f"{ded:.2f} € potenzialmente agevolabili",
            "detail": "Spese classificate come detraibili o deducibili: verifica col commercialista.",
        })
    to_verify = next(
        (f["total"] for f in fiscal if f["classification"] == "da_verificare"), 0
    )
    if to_verify:
        out.append({
            "severity": "warning",
            "icon": "❓",
            "title": f"{to_verify:.2f} € con classificazione da verificare",
            "detail": "Alcune spese non hanno una classificazione fiscale certa: rivedile per non perdere agevolazioni.",
        })

    # 5) Documenti da rivedere.
    to_review = overview_data.get("to_review", 0)
    if to_review:
        out.append({
            "severity": "warning",
            "icon": "🔎",
            "title": f"{to_review} document{'o' if to_review == 1 else 'i'} da rivedere",
            "detail": "Controlla attribuzione e classificazione prima di usarli col commercialista.",
        })

    # 6) Bollette scadute / in arrivo.
    overdue = upcoming_bills.get("overdue", [])
    if overdue:
        tot = sum(b.get("total_amount") or 0 for b in overdue)
        out.append({
            "severity": "warning",
            "icon": "⏰",
            "title": f"{len(overdue)} bollett{'a' if len(overdue) == 1 else 'e'} scadut{'a' if len(overdue) == 1 else 'e'}",
            "detail": f"Totale non saldato in ritardo: {tot:.2f} €.",
        })
    elif upcoming_bills.get("open_count"):
        out.append({
            "severity": "info",
            "icon": "📅",
            "title": f"{upcoming_bills['open_count']} bollett{'a' if upcoming_bills['open_count'] == 1 else 'e'} da pagare",
            "detail": f"Totale aperto: {upcoming_bills.get('open_total') or 0:.2f} €.",
        })

    if not out:
        out.append({
            "severity": "info",
            "icon": "📭",
            "title": "Ancora pochi dati per l'analisi",
            "detail": "Carica qualche documento o registra delle spese per vedere qui le osservazioni automatiche.",
        })
    return out


async def insights(
    db: AsyncSession,
    household_id: uuid.UUID,
    year: int,
    is_admin: bool = True,
):
    """Osservazioni automatiche sulla situazione di spesa del nucleo per l'anno
    indicato (variazioni, voci principali, potenziale fiscale, scadenze)."""
    overview_data = await overview(db, household_id, year)
    comparison = await compare_years(db, household_id, year, is_admin)
    categories = await by_category(db, household_id, year)
    if not is_admin:
        categories = [c for c in categories if c["category"] not in SENSITIVE_CATEGORIES]
    fiscal = await fiscal_summary(db, household_id, year)
    upcoming_bills = await bills_service.upcoming(db, household_id)
    return _compute_insights(
        year, overview_data, comparison, categories, fiscal, upcoming_bills
    )
