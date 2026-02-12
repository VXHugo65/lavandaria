from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.http import HttpResponse, HttpResponseBadRequest
from .models import Pedido, Cliente, Lavandaria, ItemPedido
from django.template.loader import render_to_string
import json
from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncDate
from django.utils.timezone import now, timedelta, localtime
from django.db import models
from django.utils.html import format_html
from PIL import Image, ImageDraw, ImageFont
import io
import base64
import os
from django.conf import settings


today = localtime().date()

# Calcular a data inicial e o intervalo de 7 dias
data_inicial = now().date() - timedelta(days=6)
datas_intervalo = [(data_inicial + timedelta(days=i)) for i in range(7)]


font_path = os.path.join(settings.BASE_DIR, "static/font/Roboto.ttf")


def imprimir_recibo_imagem(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id)

    # Buscar todos os pedidos não pagos do mesmo cliente
    pedido_nao_pagos = (
        Pedido.objects
        .filter(cliente=pedido.cliente, pago=False)
        .order_by('-criado_em')
    )[:3]

    todos_pedidos_nao_pagos = (
        Pedido.objects
        .filter(cliente=pedido.cliente, pago=False)
        .order_by('-criado_em')
    )
    # Calcular o total em dívida
    total_em_divida = todos_pedidos_nao_pagos.aggregate(total=Sum('total'))['total'] or 0

    pontos_do_cliente = (
        Pedido.objects
        .filter(cliente=pedido.cliente).count()
    )

    recibo_texto = render_to_string('core/recibo_termico.txt', {
        'pedido': pedido,
        
        'total_em_divida': total_em_divida,
        'pontos_do_cliente': pontos_do_cliente
    })

    # Ajuste do tamanho da fonte e cálculo da altura
    try:
        # font = ImageFont.truetype(font_path, 19)
        font = ImageFont.load_default(size=18)
    except IOError:
        font = ImageFont.load_default(size=21)

    # Calcular a altura da imagem com base no texto
    largura = 400
    altura_texto = 0
    draw = ImageDraw.Draw(Image.new("RGB", (largura, 1)))  # Usar uma imagem temporária para medir o texto

    # Usar textbbox para calcular o tamanho do texto
    for linha in recibo_texto.split('\n'):
        _, _, _, altura_linha = draw.textbbox((0, 0), linha, font=font)  # Retorna as coordenadas da caixa delimitadora
        altura_texto += altura_linha + 6  # +4 para o espaçamento entre as linhas
    
     # ===== ESPAÇO EXTRA PARA O LOGO =====
    espaco_logo = 100
    altura = max(altura_texto + espaco_logo, 200)

    img = Image.new("RGB", (largura, altura), "white")
    draw = ImageDraw.Draw(img)

    # ===== LOGOTIPO (ADICIONADO) =====
    try:
        logo_path = os.path.join(settings.BASE_DIR, "static/img/local/logo.jpg")
        logo = Image.open(logo_path).convert("RGBA")
        logo = logo.resize((160, 100))

        x_logo = (largura - logo.width) // 2
        img.paste(logo, (x_logo, 10), logo)
    except Exception:
        pass  # se não houver logo, ignora

    # ===== TEXTO (IGUAL AO TEU, SÓ DESCEU O Y) =====
    draw.multiline_text(
        (10, espaco_logo),
        recibo_texto,
        fill="black",
        font=font,
        spacing=4
    )

    # Salvar a imagem em Base64 para exibir no HTML
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return render(request, 'core/imprimir_recibo.html', {'img_base64': img_base64})

def meu_pedido(request):
    if request.method == 'POST':
        pedido_id = request.POST.get('pedido_id')

        if not pedido_id:
            return HttpResponseBadRequest("Pedido ID não fornecido.")

        return redirect(reverse('core:order-details', args=[pedido_id]))

    return render(request, 'core/order_tracking_form.html')


def meu_pedido_details(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id)
    itens_pedidos = ItemPedido.objects.filter(pedido=pedido)

    return render(request, 'core/order_details.html', {'pedido': pedido, 'itens_pedidos': itens_pedidos})


def dashboard_callback(request, context):
    total_pedidos = Pedido.objects.all().count()
    pedidos_nao_pagos = Pedido.objects.filter(pago=False).count()
    total_clientes = Cliente.objects.all().count()

    pedidos_pagos = Pedido.objects.filter(pago=True)

    # Calculando os pedidos e vendas por dia
    pedidos_por_dia = pedidos_pagos.filter(
        criado_em__date__gte=data_inicial
    ).annotate(
        data=TruncDate('criado_em')
    ).values('data').annotate(
        total_pedidos=Count('id'),
        total_vendas=Sum('total')  # Soma total sem conflito
    )

    # Dicionário de pedidos por data
    pedidos_dict = {str(p['data']): p['total_pedidos'] for p in pedidos_por_dia}
    # Dicionário de vendas por data, convertendo Decimal para float
    vendas_dict = {str(p['data']): float(p['total_vendas'] or 0) for p in pedidos_por_dia}

    labels = [str(data) for data in datas_intervalo]
    data_pedidos = [pedidos_dict.get(str(data), 0) for data in datas_intervalo]
    data_vendas = [vendas_dict.get(str(data), 0) for data in datas_intervalo]

    # lavandarias = Lavandaria.objects.annotate(
    #     numero_pedidos=Count('pedidos'),
    #     total_vendas=Sum('pedidos__total', filter=models.Q(pedidos__pago=True))  # Somente pedidos pagos
    # )
    lavandarias = Lavandaria.objects.annotate(
        numero_pedidos=Count('pedidos', filter=models.Q(pedidos__criado_em__date=today)),
        total_vendas=Sum(
            'pedidos__total',
            filter=models.Q(pedidos__criado_em__date=today, pedidos__pago=True)  # Apenas pedidos pagos
        )
    )
    vendas_por_lavandaria = (
        Pedido.objects
        .filter(criado_em__date=today, pago=True)  # Apenas pedidos pagos
        .select_related('lavandaria')  # Certifica que a relação está sendo carregada
        .values('lavandaria_id', 'lavandaria__nome', 'metodo_pagamento')  # Evita erro de chave
        .annotate(total_vendas=Sum('total'))  # Somar os totais
        .order_by('lavandaria__nome', 'metodo_pagamento')  # Ordenação
    )

    total_vendas = Pedido.objects.filter(pago=True).aggregate(Sum('total'))['total__sum']

    context.update(
        {
            "kpis": [
                {
                    "title": "Total orders",
                    "metric": total_pedidos,
                },
                {
                    "title": "Total sales",
                    "metric": str(float(total_vendas or 0)) + ' MZN',  # Convertendo para float
                },
                {
                    "title": "Total unpaid invoices",
                    "metric": pedidos_nao_pagos,
                },
                {
                    "title": "Total Active Customers",
                    "metric": total_clientes,
                },
            ],

            # Dados para o gráfico de pedidos
            'pedidosChartData': json.dumps({
                'datasets': [
                    {
                        'data': data_pedidos,
                        'borderColor': 'rgb(75, 192, 192)',  # Cor para pedidos
                        'label': 'Total de Pedidos por Dia',
                        'fill': False  # Linha sem preenchimento
                    }
                ],
                'labels': labels
            }),

            # Dados para o gráfico de vendas
            'vendasChartData': json.dumps({
                'datasets': [
                    {
                        'data': data_vendas,
                        'borderColor': 'rgb(147, 51, 234)',  # Cor para vendas
                        'label': 'Total de Vendas por Dia',
                        'fill': False  # Linha sem preenchimento
                    }
                ],
                'labels': labels
            }),

            "table": {
                "headers": ["Lavandaria", "Método de Pagamento", "Total Diário"],
                "rows": [
                    [
                        venda.get("lavandaria__nome", "Desconhecida"),  # Evita erro caso esteja faltando
                        venda.get("metodo_pagamento", "Indefinido").replace("_", " ").title(),
                        f"{float(venda.get('total_vendas', 0) or 0):,.2f} MZN"
                    ]
                    for venda in vendas_por_lavandaria
                ]
            }
        }
    )
    return context












