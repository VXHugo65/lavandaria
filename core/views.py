from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.http import HttpResponseBadRequest
from .models import Pedido, Cliente, Lavandaria, ItemPedido, PagamentoPedido
from django.template.loader import render_to_string
import json
from django.db.models import (
    Count, Sum, F, OuterRef, Subquery, DecimalField, Value
)
from django.db.models.functions import TruncDate, Coalesce
from django.utils.timezone import now, timedelta, localtime
from django.db import models
from PIL import Image, ImageDraw, ImageFont
import io
import base64
import os
from django.conf import settings
from .models import MovimentacaoPontos

from decimal import Decimal
from django.db.models import DecimalField, Value


today = localtime().date()

# Calcular a data inicial e o intervalo de 7 dias
data_inicial = now().date() - timedelta(days=6)
datas_intervalo = [(data_inicial + timedelta(days=i)) for i in range(7)]

font_path = os.path.join(settings.BASE_DIR, "static/font/Roboto.ttf")


def imprimir_recibo_imagem(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id)

    # Subquery: soma pagamentos por pedido
    pagos_subq = (
        PagamentoPedido.objects
        .filter(pedido=OuterRef("pk"))
        .values("pedido")
        .annotate(s=Sum("valor"))
        .values("s")[:1]
    )

    # Buscar todos os pedidos não pagos do mesmo cliente (inclui parcial)
    pedidos_nao_pagos = (
        Pedido.objects
        .filter(cliente=pedido.cliente)
        .exclude(status_pagamento="pago")
        .annotate(
            valor_pago_calc=Coalesce(
                Subquery(pagos_subq),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
        .annotate(
            saldo_calc=Coalesce(
                F("total") - F("valor_pago_calc"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
        .order_by("-criado_em")
    )[:3]

    # ✅ Total em dívida (Decimal safe)
    total_em_divida = (
        Pedido.objects
        .filter(cliente=pedido.cliente)
        .exclude(status_pagamento="pago")
        .annotate(
            valor_pago_calc=Coalesce(
                Subquery(pagos_subq),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
        .annotate(
            saldo_calc=Coalesce(
                F("total") - F("valor_pago_calc"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
        .aggregate(
            total=Coalesce(
                Sum("saldo_calc"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["total"]
    )

    # ✅ Valor pago neste pedido (soma dos pagamentos)
    valor_pago = (
        PagamentoPedido.objects
        .filter(pedido=pedido)
        .aggregate(
            total=Coalesce(
                Sum("valor"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["total"]
    )

    saldo = (pedido.total or Decimal("0.00")) - (valor_pago or Decimal("0.00"))
    if saldo < 0:
        saldo = Decimal("0.00")

    ultimo_metodo_pagamento = (
        PagamentoPedido.objects
        .filter(pedido=pedido)
        .order_by("-pago_em", "-id")
        .values_list("metodo_pagamento", flat=True)
        .first()
    )
    ultimo_metodo_pagamento_label = None
    if ultimo_metodo_pagamento:
        ultimo_metodo_pagamento_label = ultimo_metodo_pagamento.replace("_", " ").title()

    mov = MovimentacaoPontos.objects.filter(
        pedido=pedido,
        tipo="ganho"
    ).first()

    # 🎯 Verificar se o pagamento foi feito com pontos
    pagamento_pontos = PagamentoPedido.objects.filter(
        pedido=pedido,
        metodo_pagamento="pontos"
    ).exists()

    # 🎯 Pontos só aparecem se NÃO for pagamento com pontos
    if pagamento_pontos:
        pontos_totais = 0
        equivalente_mzn = Decimal("0.00")
    else:
        pontos_totais = pedido.cliente.pontos
        equivalente_mzn = Decimal(pontos_totais) * Decimal("0.10")

    pontos_ganhos = mov.pontos if mov else 0

    pontos_totais = pedido.cliente.pontos
    equivalente_mzn = Decimal(pontos_totais) * Decimal("0.10")




    recibo_texto = render_to_string("core/recibo_termico.txt", {
        "pedido": pedido,
        "pedidos_nao_pagos": pedidos_nao_pagos,
        "total_em_divida": total_em_divida,


        "valor_pago": valor_pago,
        "saldo": saldo,
        "ultimo_metodo_pagamento": ultimo_metodo_pagamento,
        "ultimo_metodo_pagamento_label": ultimo_metodo_pagamento_label,

        # 🎁 pontos
        "pontos_ganhos": pontos_ganhos,
        "pontos_totais": pontos_totais,
        "equivalente_mzn": equivalente_mzn,
    })

    # Ajuste do tamanho da fonte e cálculo da altura
    try:
        font = ImageFont.load_default(size=18)
    except IOError:
        font = ImageFont.load_default(size=21)

    largura = 400
    altura_texto = 0
    draw = ImageDraw.Draw(Image.new("RGB", (largura, 1)))

    for linha in recibo_texto.split("\n"):
        _, _, _, altura_linha = draw.textbbox((0, 0), linha, font=font)
        altura_texto += altura_linha + 6

    espaco_logo = 100
    altura = max(altura_texto + espaco_logo, 200)

    img = Image.new("RGB", (largura, altura), "white")
    draw = ImageDraw.Draw(img)

    # LOGO
    try:
        logo_path = os.path.join(settings.BASE_DIR, "static/img/local/logo.jpg")
        logo = Image.open(logo_path).convert("RGBA")
        logo = logo.resize((160, 100))

        x_logo = (largura - logo.width) // 2
        img.paste(logo, (x_logo, 10), logo)
    except Exception:
        pass

    draw.multiline_text(
        (10, espaco_logo),
        recibo_texto,
        fill="black",
        font=font,
        spacing=4
    )

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return render(request, "core/imprimir_recibo.html", {"img_base64": img_base64})


def meu_pedido(request):
    if request.method == "POST":
        pedido_id = request.POST.get("pedido_id")
        if not pedido_id:
            return HttpResponseBadRequest("Pedido ID não fornecido.")
        return redirect(reverse("core:order-details", args=[pedido_id]))

    return render(request, "core/order_tracking_form.html")


def meu_pedido_details(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id)
    itens_pedidos = ItemPedido.objects.filter(pedido=pedido)
    return render(request, "core/order_details.html", {"pedido": pedido, "itens_pedidos": itens_pedidos})


def dashboard_callback(request, context):
    total_pedidos = Pedido.objects.count()

    # Para parcial: "não pago" = status_pagamento != pago
    pedidos_nao_pagos = Pedido.objects.exclude(status_pagamento="pago").count()

    total_clientes = Cliente.objects.count()

    # Pedidos pagos (quitados)
    pedidos_pagos = Pedido.objects.filter(status_pagamento="pago")

    # Pedidos e vendas por dia (últimos 7 dias) — baseado em pedidos quitados
    pedidos_por_dia = (
        pedidos_pagos.filter(criado_em__date__gte=data_inicial)
        .annotate(data=TruncDate("criado_em"))
        .values("data")
        .annotate(
            total_pedidos=Count("id"),
            total_vendas=Coalesce(
                Sum("total"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
        )
    )

    pedidos_dict = {str(p["data"]): p["total_pedidos"] for p in pedidos_por_dia}
    vendas_dict = {str(p["data"]): float(p["total_vendas"] or 0) for p in pedidos_por_dia}

    labels = [str(data) for data in datas_intervalo]
    data_pedidos = [pedidos_dict.get(str(data), 0) for data in datas_intervalo]
    data_vendas = [vendas_dict.get(str(data), 0) for data in datas_intervalo]

    # Lavandarias: pedidos do dia + vendas do dia (quitados)
    lavandarias = Lavandaria.objects.annotate(
        numero_pedidos=Count("pedidos", filter=models.Q(pedidos__criado_em__date=today)),
        total_vendas=Coalesce(
            Sum(
                "pedidos__total",
                filter=models.Q(pedidos__criado_em__date=today, pedidos__status_pagamento="pago"),
            ),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
    )

    # Vendas por lavandaria e método: baseado em PagamentoPedido (recebimentos reais)
    vendas_por_lavandaria = (
        PagamentoPedido.objects
        .filter(pedido__criado_em__date=today)  # ou pago_em__date=today se quiser “caixa do dia”
        .select_related("pedido__lavandaria")
        .values("pedido__lavandaria_id", "pedido__lavandaria__nome", "metodo_pagamento")
        .annotate(
            total_vendas=Coalesce(
                Sum("valor"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
        .order_by("pedido__lavandaria__nome", "metodo_pagamento")
    )

    total_vendas = PagamentoPedido.objects.aggregate(
        total=Coalesce(
            Sum("valor"),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )["total"]

    context.update(
        {
            "kpis": [
                {"title": "Total orders", "metric": total_pedidos},
                {"title": "Total sales", "metric": f"{float(total_vendas or 0):.2f} MZN"},
                {"title": "Total unpaid invoices", "metric": pedidos_nao_pagos},
                {"title": "Total Active Customers", "metric": total_clientes},
            ],
            "pedidosChartData": json.dumps({
                "datasets": [{
                    "data": data_pedidos,
                    "borderColor": "rgb(75, 192, 192)",
                    "label": "Total de Pedidos por Dia",
                    "fill": False
                }],
                "labels": labels
            }),
            "vendasChartData": json.dumps({
                "datasets": [{
                    "data": data_vendas,
                    "borderColor": "rgb(147, 51, 234)",
                    "label": "Total de Vendas por Dia",
                    "fill": False
                }],
                "labels": labels
            }),
            "table": {
                "headers": ["Lavandaria", "Método de Pagamento", "Total Diário"],
                "rows": [
                    [
                        venda.get("pedido__lavandaria__nome", "Desconhecida"),
                        venda.get("metodo_pagamento", "Indefinido").replace("_", " ").title(),
                        f"{float(venda.get('total_vendas', 0) or 0):,.2f} MZN",
                    ]
                    for venda in vendas_por_lavandaria
                ]
            }
        }
    )
    return context
