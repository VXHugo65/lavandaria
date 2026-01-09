from datetime import timedelta
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Count, Sum, Avg, Max, Min, Q
from django.utils import timezone

from core.models import Cliente, Pedido


@staff_member_required
def crm_pos_venda(request):
    hoje = timezone.now()
    limite_ativos = hoje - timedelta(days=30)
    limite_risco = hoje - timedelta(days=45)
    ultimos_7_dias = hoje - timedelta(days=6)

    # ======================
    # FILTROS (GET)
    # ======================
    search = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "")
    atividade_filter = request.GET.get("atividade", "")
    page_number = request.GET.get("page", 1)

    # ======================
    # QUERYSET BASE
    # ======================
    clientes_qs = Cliente.objects.annotate(
        total_pedidos=Count("pedidos"),
        total_gasto=Sum("pedidos__total"),
        ultima_visita=Max("pedidos__criado_em"),
        primeira_visita=Min("pedidos__criado_em"),
    )

    # ======================
    # SEARCH
    # ======================
    if search:
        clientes_qs = clientes_qs.filter(
            Q(id__icontains=search) |
            Q(nome__icontains=search)
        )

    # ======================
    # FILTRO ATIVIDADE (DB)
    # ======================
    if atividade_filter == "ativo":
        clientes_qs = clientes_qs.filter(ultima_visita__gte=limite_ativos)

    elif atividade_filter == "risco":
        clientes_qs = clientes_qs.filter(
            ultima_visita__lt=limite_ativos,
            ultima_visita__gte=limite_risco
        )

    elif atividade_filter == "inativo":
        clientes_qs = clientes_qs.filter(ultima_visita__lt=limite_risco)

    clientes_qs = clientes_qs.order_by("-total_gasto")

    # ======================
    # KPIs PÓS-VENDA
    # ======================
    total_clientes = Cliente.objects.count()

    clientes_ativos = Cliente.objects.filter(
        pedidos__criado_em__gte=limite_ativos
    ).distinct().count()

    clientes_inativos = total_clientes - clientes_ativos

    clientes_em_risco = Cliente.objects.filter(
        pedidos__criado_em__lt=limite_risco
    ).distinct().count()

    clientes_recorrentes = Cliente.objects.annotate(
        total_pedidos=Count("pedidos")
    ).filter(total_pedidos__gte=2).count()

    ticket_medio = Pedido.objects.aggregate(
        v=Avg("total")
    )["v"] or 0

    ltv_medio = Cliente.objects.annotate(
        total_gasto=Sum("pedidos__total")
    ).aggregate(
        m=Avg("total_gasto")
    )["m"] or 0

    pedidos_nao_pagos = Pedido.objects.filter(pago=False).count()

    clientes_vip = Cliente.objects.annotate(
        total_gasto=Sum("pedidos__total")
    ).filter(total_gasto__gte=10000).count()

    kpis = [
        {"title": "Clientes Ativos", "metric": clientes_ativos},
        {"title": "Clientes Inativos", "metric": clientes_inativos},
        {"title": "Clientes em Risco", "metric": clientes_em_risco},
        {"title": "Clientes Recorrentes", "metric": clientes_recorrentes},
        {"title": "Ticket Médio", "metric": f"{ticket_medio:.2f} MT"},
        {"title": "LTV Médio", "metric": f"{ltv_medio:.2f} MT"},
        {"title": "Clientes VIP", "metric": clientes_vip},
        {"title": "Pedidos Não Pagos", "metric": pedidos_nao_pagos},
    ]

    # ======================
    # GRÁFICO – PEDIDOS (7 DIAS)
    # ======================
    pedidos_qs = (
        Pedido.objects
        .filter(criado_em__date__gte=ultimos_7_dias.date())
        .extra(select={"dia": "DATE(criado_em)"})
        .values("dia")
        .annotate(total=Count("id"))
        .order_by("dia")
    )

    labels = []
    pedidos_data = []

    for i in range(7):
        dia = (ultimos_7_dias + timedelta(days=i)).date()
        labels.append(dia.strftime("%d/%m"))
        valor = next((p["total"] for p in pedidos_qs if p["dia"] == dia), 0)
        pedidos_data.append(valor)

    pedidosChartData = {
        "labels": labels,
        "datasets": [{
            "label": "Pedidos",
            "data": pedidos_data,
        }]
    }

    # ======================
    # GRÁFICO – VENDAS (7 DIAS)
    # ======================
    vendas_qs = (
        Pedido.objects
        .filter(criado_em__date__gte=ultimos_7_dias.date())
        .extra(select={"dia": "DATE(criado_em)"})
        .values("dia")
        .annotate(total=Sum("total"))
        .order_by("dia")
    )

    vendas_data = []

    for i in range(7):
        dia = (ultimos_7_dias + timedelta(days=i)).date()
        valor = next((v["total"] for v in vendas_qs if v["dia"] == dia), 0)
        vendas_data.append(float(valor or 0))

    vendasChartData = {
        "labels": labels,
        "datasets": [{
            "label": "Vendas",
            "data": vendas_data,
        }]
    }

    # ======================
    # PAGINAÇÃO
    # ======================
    paginator = Paginator(clientes_qs, 10)  # 10 clientes por página
    page_obj = paginator.get_page(page_number)

    # ======================
    # TABELA – CLIENTES (COM STATUS)
    # ======================
    tabela = []

    for c in page_obj:
        dias_sem_visita = (
            (hoje.date() - c.ultima_visita.date()).days
            if c.ultima_visita else None
        )

        # ---- ATIVIDADE ----
        if dias_sem_visita is None or dias_sem_visita > 45:
            atividade = "inativo"
        elif dias_sem_visita > 30:
            atividade = "risco"
        else:
            atividade = "ativo"

        # ---- STATUS ----
        if c.total_gasto and c.total_gasto >= 10000:
            status = "VIP"
        elif c.total_pedidos >= 5:
            status = "Regular"
        elif c.total_pedidos > 0:
            status = "Ocasional"
        else:
            status = "Inativo"

        # ---- FILTRO STATUS (PYTHON) ----
        if status_filter and status != status_filter:
            continue

        tabela.append({
            "id": c.id,
            "cliente": c.nome,
            "pedidos": c.total_pedidos or 0,
            "ultima_visita": (
                f"{dias_sem_visita} dias"
                if dias_sem_visita is not None else "Nunca"
            ),
            "total": f"{(c.total_gasto or 0):.2f} MT",
            "status": status,
            "atividade": atividade,
        })

    # ======================
    # CONTEXTO
    # ======================
    context = {
        "title": "CRM Pós-Venda",
        "kpis": kpis,
        "pedidosChartData": pedidosChartData,
        "vendasChartData": vendasChartData,
        "table": {
            "headers": [
                "ID",
                "Cliente",
                "Pedidos",
                "Última Visita",
                "Total Gasto",
                "Status",
            ],
            "rows": tabela,
        },
        "page_obj": page_obj,
        "filters": {
            "q": search,
            "status": status_filter,
            "atividade": atividade_filter,
        }
    }

    return render(request, "crm/crm_dashboard.html", context)
