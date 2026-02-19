from django.contrib import admin
from unfold.admin import ModelAdmin, StackedInline
from .models import Lavandaria, ItemServico, Servico, Cliente, Pedido, ItemPedido, Funcionario, Recibo, PagamentoPedido
from django.utils.html import format_html
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from django.contrib.auth.models import Group, User
from django.contrib import messages
import requests
import json
from django.urls import reverse
from import_export.admin import ImportExportModelAdmin
from unfold.contrib.import_export.forms import ExportForm, ImportForm
from unfold.contrib.filters.admin import RangeDateTimeFilter
from django.template.loader import render_to_string
from xhtml2pdf import pisa
from io import BytesIO
from django.http import HttpResponse
from datetime import datetime
from django.utils import timezone

from decimal import Decimal
from django.contrib import admin, messages
from django.db.models import Sum, DecimalField, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.urls import path, reverse
from django.shortcuts import redirect
from django.utils.html import format_html

from unfold.admin import ModelAdmin
from .models import Pedido, PagamentoPedido, Funcionario

admin.site.unregister(Group)
admin.site.unregister(User)


def gerar_relatorio_pdf(modeladmin, request, queryset):
    # 🔥 Otimiza queryset para evitar N+1 queries
    queryset = queryset.prefetch_related('itens')

    # 🔥 Processa os totais por pedido
    for pedido in queryset:
        itens = pedido.itens.all()
        pedido.total_quantidade = sum(item.quantidade for item in itens)
        pedido.total_valor = sum(item.preco_total for item in itens)

    # 🔥 Totais gerais
    total_quantidade = sum(pedido.total_quantidade for pedido in queryset)
    total_valor = sum(pedido.total_valor for pedido in queryset)

    # 🔥 Datas do relatório
    if queryset.exists():
        start_date = timezone.localtime(queryset.first().criado_em).strftime('%d/%m/%Y')
        end_date = timezone.localtime(queryset.last().criado_em).strftime('%d/%m/%Y')
    else:
        start_date = end_date = datetime.today().strftime('%d/%m/%Y')

    # 🔥 Renderiza HTML
    html_string = render_to_string('core/relatorio_vendas.html', {
        'pedidos': queryset,
        'total_quantidade': total_quantidade,
        'total_valor': total_valor,
        'start_date': start_date,
        'end_date': end_date
    })

    # 🔥 Cria PDF
    buffer = BytesIO()
    filename = f"relatorio_vendas_{start_date}_a_{end_date}.pdf"
    pisa_status = pisa.CreatePDF(html_string, dest=buffer)

    # 🔥 Verifica erros
    if pisa_status.err:
        return HttpResponse("Erro ao gerar PDF", content_type="text/plain")

    buffer.seek(0)
    response = HttpResponse(buffer, content_type="application/pdf")
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


from django.db.models import Sum, Count
from django.db.models.functions import Coalesce

DECIMAL_0 = Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))


def gerar_relatorio_financeiro(modeladmin, request, queryset):
    """
    RELATÓRIO FINANCEIRO (Caixa) — por recebimentos (PagamentoPedido).
    Funciona com pagamentos parciais.
    """

    qs_pedidos = (
        queryset
        .select_related("cliente", "lavandaria", "funcionario")
        .order_by("criado_em")
    )

    # janela “visual” do relatório (baseada nos pedidos selecionados)
    if qs_pedidos.exists():
        start_dt = qs_pedidos.first().criado_em
        end_dt = qs_pedidos.last().criado_em
    else:
        now = timezone.now()
        start_dt = now - timezone.timedelta(days=1)
        end_dt = now

    # Pagamentos (recebimentos) pertencentes aos pedidos selecionados
    pagamentos = (
        PagamentoPedido.objects
        .filter(pedido__in=qs_pedidos)
        .select_related("pedido", "pedido__cliente", "pedido__lavandaria", "criado_por", "criado_por__user")
        .order_by("pago_em", "id")
    )

    # ===== TOTAIS =====
    total_faturado = qs_pedidos.aggregate(
        t=Coalesce(Sum("total"), DECIMAL_0)
    )["t"]

    total_recebido = pagamentos.aggregate(
        t=Coalesce(Sum("valor"), DECIMAL_0)
    )["t"]

    # saldo por pedido (sem usar annotate "saldo" pra não bater com property)
    saldo_total = Decimal("0.00")
    pedidos_em_aberto = []
    for p in qs_pedidos:
        recebido_p = (
            PagamentoPedido.objects
            .filter(pedido=p)
            .aggregate(t=Coalesce(Sum("valor"), DECIMAL_0))["t"]
        )
        saldo = (p.total or Decimal("0.00")) - (recebido_p or Decimal("0.00"))
        if saldo > 0:
            pedidos_em_aberto.append({
                "pedido": p,
                "recebido": recebido_p,
                "saldo": saldo,
            })
            saldo_total += saldo

    # ===== RESUMOS =====

    # por método
    resumo_por_metodo = (
        pagamentos.values("metodo_pagamento")
        .annotate(
            qtd=Count("id"),
            total=Coalesce(Sum("valor"), DECIMAL_0),
        )
        .order_by("-total")
    )

    # por dia (caixa) — baseado no dia do pagamento
    resumo_por_dia = (
        pagamentos
        .values("pago_em__date")
        .annotate(
            qtd=Count("id"),
            total=Coalesce(Sum("valor"), DECIMAL_0),
        )
        .order_by("pago_em__date")
    )

    # por lavandaria (se tiver multi)
    resumo_por_lavandaria = (
        pagamentos
        .values("pedido__lavandaria__nome")
        .annotate(
            qtd=Count("id"),
            total=Coalesce(Sum("valor"), DECIMAL_0),
        )
        .order_by("-total")
    )

    # por caixa (funcionário)
    resumo_por_caixa = (
        pagamentos
        .values("criado_por__user__username")
        .annotate(
            qtd=Count("id"),
            total=Coalesce(Sum("valor"), DECIMAL_0),
        )
        .order_by("-total")
    )

    # Lavandaria “do usuário” (se existir)
    try:
        lavandaria = request.user.funcionario.lavandaria
    except Exception:
        lavandaria = None

    start_date = timezone.localtime(start_dt).strftime("%d/%m/%Y")
    end_date = timezone.localtime(end_dt).strftime("%d/%m/%Y")

    html_string = render_to_string("core/relatorio_financeiro.html", {
        "lavandaria": lavandaria,

        "start_date": start_date,
        "end_date": end_date,

        "total_faturado": total_faturado,
        "total_recebido": total_recebido,
        "saldo_total": saldo_total,

        "resumo_por_metodo": resumo_por_metodo,
        "resumo_por_dia": resumo_por_dia,
        "resumo_por_lavandaria": resumo_por_lavandaria,
        "resumo_por_caixa": resumo_por_caixa,

        "pagamentos": pagamentos,
        "pedidos_em_aberto": pedidos_em_aberto,  # lista de dicts: pedido/recebido/saldo
        "pedidos": qs_pedidos,
    })

    buffer = BytesIO()
    filename = f"relatorio_financeiro_{start_date}_a_{end_date}.pdf"
    pisa_status = pisa.CreatePDF(html_string, dest=buffer)

    if pisa_status.err:
        return HttpResponse("Erro ao gerar PDF", content_type="text/plain")

    buffer.seek(0)
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin, ImportExportModelAdmin):
    import_form_class = ImportForm
    export_form_class = ExportForm
    # Forms loaded from `unfold.forms`
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin, ImportExportModelAdmin):
    import_form_class = ImportForm
    export_form_class = ExportForm
    pass


# Inline para gerenciar os itens de pedido diretamente no pedido
class ItemPedidoInline(StackedInline):
    model = ItemPedido
    extra = 0
    fields = [
        ('item_de_servico',),
        ('descricao', 'quantidade', 'preco_total'),
    ]
    autocomplete_fields = ('item_de_servico',)
    readonly_fields = ('preco_total',)


class PagamentoPedidoInline(StackedInline):
    model = PagamentoPedido
    extra = 0
    fields = (
        ("valor", "metodo_pagamento"),
        ("pago_em", "criado_por"),
    )
    readonly_fields = ("pago_em", "criado_por")

    def save_new_instance(self, form, commit=True):
        obj = super().save_new_instance(form, commit=False)
        try:
            obj.criado_por = Funcionario.objects.get(user=self.request.user)
        except Funcionario.DoesNotExist:
            obj.criado_por = None
        if commit:
            obj.save()
        return obj


# Configuração do modelo Lavandaria no Admin
@admin.register(Lavandaria)
class LavandariaAdmin(ModelAdmin, ImportExportModelAdmin):
    import_form_class = ImportForm
    export_form_class = ExportForm
    list_display = ('nome', 'endereco', 'telefone', 'criado_em')
    search_fields = ('nome', 'telefone')
    list_filter = ('criado_em',)
    fieldsets = (
        ('Informações Básicas', {'fields': ('nome', 'endereco', 'telefone')}),
        ('Datas', {'fields': ('criado_em',)}),
    )
    readonly_fields = ('criado_em',)


# Configuração do modelo Cliente no Admin
@admin.register(Cliente)
class ClienteAdmin(ModelAdmin, ImportExportModelAdmin):
    import_form_class = ImportForm
    export_form_class = ExportForm
    list_display = ('id', 'nome', 'telefone', 'endereco')
    search_fields = ('nome', 'telefone')


# Configuração do modelo Funcionario no Admin
@admin.register(Funcionario)
class FuncionarioAdmin(ModelAdmin, ImportExportModelAdmin):
    import_form_class = ImportForm
    export_form_class = ExportForm
    list_display = ('user', 'lavandaria', 'grupo', 'telefone')
    search_fields = ('user__username', 'telefone', 'lavandaria__nome')
    list_filter = ('grupo',)


# Configuração do modelo ItemServico no Admin
@admin.register(ItemServico)
class ItemServicoAdmin(ModelAdmin, ImportExportModelAdmin):
    list_display = ('nome', 'preco_base', 'disponivel')
    search_fields = ('nome',)
    list_filter = ('disponivel',)
    import_form_class = ImportForm
    export_form_class = ExportForm


# Configuração do modelo Servico no Admin
@admin.register(Servico)
class ServicoAdmin(ModelAdmin):
    list_display = ('nome', 'lavandaria', 'ativo')
    search_fields = ('nome', 'lavandaria__nome')
    list_filter = ('ativo', 'lavandaria')
    fieldsets = (
        ('Informações do Serviço', {'fields': ('nome', 'descricao', 'ativo')}),
        ('Lavandaria', {'fields': ('lavandaria',)}),
    )


API_URL = 'https://api.mozesms.com/v2/sms/bulk'
BEARER_TOKEN = 'Bearer 2374:zKNUpX-J4dao9-VEi60O-UeNqdN'
SENDER_ID = "POWERWASH"


def enviar_sms_mozesms(numero, mensagem):
    """
    Envia um SMS usando a API Mozesms (nova versão).
    """
    payload = {
        'sender_id': SENDER_ID,
        'messages': [
            {
                'phone': numero,
                'message': mensagem
            }
        ]
    }

    headers = {
        'Content-Type': 'application/json',
        'Authorization': BEARER_TOKEN
    }

    try:
        response = requests.post(API_URL, json=payload, headers=headers)

        if response.status_code == 200:
            try:
                json_resposta = response.json()

                if json_resposta.get('success'):
                    print("SMS enviado com sucesso!", json_resposta)
                    return True
                else:
                    print("Erro ao enviar SMS:", json_resposta)
                    return False

            except Exception as e:
                print(f"Erro ao processar a resposta JSON: {e}")
                return False
        else:
            print(f"Erro na requisição: {response.status_code} - {response.text}")
            return False

    except requests.RequestException as e:
        print(f"Erro ao enviar SMS: {e}")
        return False


@admin.register(Pedido)
class PedidoAdmin(ModelAdmin, ImportExportModelAdmin):
    import_form_class = ImportForm
    export_form_class = ExportForm

    list_display = (
        "id", "cliente", "criado_em",
        "status", "status_pagamento",
        "total", "total_pago", "saldo_admin",
        "botao_imprimir"
    )
    search_fields = ("cliente__nome", "cliente__telefone", "id","itens__item_de_servico__nome",
        "itens__descricao",)
    list_display_links = ("cliente", "id")

    # ❌ Não permitir editar pagamento manualmente
    # list_editable = ("pago",)

    list_filter = (
        "status",
        "status_pagamento",
        ("criado_em", RangeDateTimeFilter),
    )
    list_filter_submit = True

    fieldsets = (
        ("Detalhes do Pedido", {"fields": ("cliente", "lavandaria", "funcionario", "status")}),
        ("Totais e Datas", {"fields": ("total", "total_pago", "criado_em")}),
        ("Pagamento", {"fields": ("status_pagamento", "pago")}),
    )

    readonly_fields = (
        "criado_em", "funcionario", "lavandaria",
        "total_pago", "status_pagamento",
        "pago",
        "total",
    )
    autocomplete_fields = ("cliente",)

    # ✅ adiciona pagamentos inline + itens
    inlines = [ItemPedidoInline, PagamentoPedidoInline]
    
    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(
            request, queryset, search_term
        )
        return queryset.distinct(), use_distinct
    

    def saldo_admin(self, obj):
        return obj.saldo

    saldo_admin.short_description = "Saldo"

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj and obj.pk:
            self._restrict_status_choices(form, obj)
        return form

    def _restrict_status_choices(self, form, obj):
        if "status" in form.base_fields:
            current_status = obj.status

            status_flow = {
                "pendente": ["pendente", "completo"],
                "completo": ["completo", "pronto"],
                "pronto": ["pronto", "entregue"],
                "entregue": ["entregue"],
            }

            allowed_statuses = status_flow.get(current_status, [current_status])
            choices = [choice for choice in form.base_fields['status'].choices
                       if choice[0] in allowed_statuses]

            form.base_fields["status"].choices = [
                c for c in form.base_fields["status"].choices
                if c[0] in allowed_statuses
            ]

            if len(allowed_statuses) == 1:
                form.base_fields["status"].disabled = True

    def save_model(self, request, obj, form, change):
        # mantém a tua lógica de atribuir funcionario/lavandaria
        try:
            funcionario = Funcionario.objects.get(user=request.user)
            obj.funcionario = funcionario
            if funcionario.lavandaria:
                obj.lavandaria = funcionario.lavandaria
            else:
                raise ValueError("O funcionário logado não está associado a nenhuma lavandaria.")
        except Funcionario.DoesNotExist:
            raise ValueError("O usuário logado não está associado a nenhum funcionário.")

        super().save_model(request, obj, form, change)

        # ✅ recalc após salvar (ex: total mudou por itens)
        try:
            obj.recalcular_pagamentos()
        except Exception:
            pass

    def save_formset(self, request, form, formset, change):
        """
        Garante:
        - criado_por preenchido em PagamentoPedido
        - recalcular_pagamentos após alterações
        """
        instances = formset.save(commit=False)

        for inst in instances:
            if isinstance(inst, PagamentoPedido) and not inst.criado_por:
                try:
                    inst.criado_por = Funcionario.objects.get(user=request.user)
                except Funcionario.DoesNotExist:
                    inst.criado_por = None
            inst.save()

        formset.save_m2m()

        obj = form.instance
        try:
            obj.recalcular_pagamentos()
        except Exception:
            pass

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        try:
            funcionario = Funcionario.objects.get(user=request.user)
            if funcionario.lavandaria:
                return qs.filter(lavandaria=funcionario.lavandaria)
            raise ValueError("O funcionário logado não está associado a nenhuma lavandaria.")
        except Funcionario.DoesNotExist:
            raise ValueError("O usuário logado não está associado a nenhum funcionário.")

    def botao_imprimir(self, obj):
        url = reverse("core:imprimir_recibo_imagem", args=[obj.id])
        return format_html(f'<a class="button" href="{url}" target="_blank">Imprimir</a>')

    botao_imprimir.short_description = "Imprimir Recibo"

    def marcar_como_completo(self, request, queryset):
        pedidos_processados = 0

        for pedido in queryset:
            if pedido.status == "pendente":
                pedido.status = "completo"
                pedido.save(update_fields=["status"])
                pedidos_processados += 1
            else:
                messages.warning(
                    request,
                    f"Pedido {pedido.id} não pode ser marcado como completo. "
                    f"Status atual: {pedido.status}"
                )
    
        if pedidos_processados:
            messages.success(
                request,
                f"{pedidos_processados} pedido(s) marcado(s) como completo."
            )
        else:
            messages.warning(request, "Nenhum pedido pôde ser processado.")


    def marcar_como_pronto(self, request, queryset):
        pedidos_processados = 0
    
    
        for pedido in queryset:
            if pedido.status == "completo":
                pedido.status = "pronto"
                pedido.save(update_fields=["status"])
                pedidos_processados += 1
            else:
                messages.warning(
                    request,
                    f"Pedido {pedido.id} não pode ser marcado como pronto. "
                    f"Status atual: {pedido.status}"
                )
        
        if pedidos_processados:
            messages.success(
                request,
                f"{pedidos_processados} pedido(s) marcado(s) como pronto."
            )
        else:
            messages.warning(request, "Nenhum pedido pôde ser processado.")


    def marcar_como_entregue(self, request, queryset):
        pedidos_processados = 0
    
    
        for pedido in queryset:
            if pedido.status == "pronto":
                pedido.status = "entregue"
                pedido.save(update_fields=["status"])
                pedidos_processados += 1
            else:
                messages.warning(
                    request,
                    f"Pedido {pedido.id} não pode ser marcado como entregue. "
                    f"Status atual: {pedido.status}"
                )
        
        if pedidos_processados:
            messages.success(
                request,
                f"{pedidos_processados} pedido(s) marcado(s) como entregue."
            )
        else:
            messages.warning(request, "Nenhum pedido pôde ser processado.")
    
    marcar_como_completo.short_description = ("Marcar como Completo (apenas pendentes)")
    marcar_como_pronto.short_description = "Marcar como Pronto (apenas completo)"
    marcar_como_entregue.short_description = "Marcar como Entregue (apenas prontos)"


    def enviar_sms_pedido_pronto(self, request, queryset):
        pedidos_notificados = 0
    
        for pedido in queryset:
            if pedido.status == 'pronto' and hasattr(pedido.cliente, 'telefone'):
                link_pedido = f"https://lavandaria-production.up.railway.app/meu-pedido/{pedido.id}"
                mensagem = (
                    f"Ola {pedido.cliente.nome}, "
                    f"o seu artigo #{pedido.id} esta pronto, para o levantamento. "
                    f"Para mais info. Clique aqui {link_pedido}"
                )
    
                resposta = enviar_sms_mozesms(pedido.cliente.telefone, mensagem)
    
                if resposta:
                    pedidos_notificados += 1
    
        if pedidos_notificados:
            messages.success(request, f"Mensagem enviada com sucesso para {pedidos_notificados} clientes.")
        else:
            messages.warning(request,
                             "ERRO. Verifique se os pedidos estão 'prontos' e se os clientes têm número de telefone.")


    # mantém as tuas actions operacionais
    actions = [
        "marcar_como_completo",
        "marcar_como_pronto",
        "marcar_como_entregue",
        "enviar_sms_pedido_pronto",
        gerar_relatorio_pdf,
        gerar_relatorio_financeiro,
    ]
    enviar_sms_pedido_pronto.short_description = "Enviar mensagem de pedido pronto"


# Configuração do modelo ItemPedido no Admin
@admin.register(ItemPedido)
class ItemPedidoAdmin(ModelAdmin):
    list_display = ('pedido', 'item_de_servico', 'quantidade', 'preco_total')
    search_fields = ('pedido__id', 'item_de_servico__nome')
    list_filter = ('servico',)
    readonly_fields = ('preco_total',)
    autocomplete_fields = ('item_de_servico',)


@admin.register(Recibo)
class ReciboAdmin(ModelAdmin):
    list_display = ('id', 'pedido', 'total_pago', 'emitido_em', 'metodo_pagamento', 'criado_por')
    autocomplete_fields = ('pedido',)
    readonly_fields = ('emitido_em', 'criado_por')

    def save_model(self, request, obj, form, change):
        try:
            # Obtém o funcionário associado ao usuário logado
            criado_por = Funcionario.objects.get(user=request.user)
            obj.funcionario = criado_por

            # Verifica se o funcionário tem uma lavandaria associada
            if criado_por.lavandaria:
                obj.lavandaria = criado_por.lavandaria
            else:
                raise ValueError("O funcionário logado não está associado a nenhuma lavandaria.")
        except Funcionario.DoesNotExist:
            raise ValueError("O usuário logado não está associado a nenhum funcionário.")

        super().save_model(request, obj, form, change)


def _total_pago(pedido: Pedido) -> Decimal:
    return (
            PagamentoPedido.objects.filter(pedido=pedido)
            .aggregate(
                total=Coalesce(
                    Sum("valor"),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )["total"]
            or Decimal("0.00")
    )


def _saldo(pedido: Pedido) -> Decimal:
    total = pedido.total or Decimal("0.00")
    pago = _total_pago(pedido)
    s = total - pago
    return s if s > 0 else Decimal("0.00")


@admin.register(PagamentoPedido)
class PagamentoPedidoAdmin(ModelAdmin):
    list_display = ("id", "pedido", "valor", "metodo_pagamento", "pago_em", "criado_por")
    list_filter = (
        "metodo_pagamento",
        ("pago_em", RangeDateTimeFilter),
    )
    search_fields = ("pedido__id", "pedido__cliente__nome", "pedido__cliente__telefone")
    autocomplete_fields = ("pedido",)
    readonly_fields = ("criado_por",)

    actions = ["receber_saldo_pedidos_selecionados"]

    def save_model(self, request, obj, form, change):
        if not obj.criado_por_id:
            obj.criado_por = Funcionario.objects.get(user=request.user)
        if not obj.pago_em:
            obj.pago_em = timezone.now()

        super().save_model(request, obj, form, change)

        # Recalcula o pedido
        if hasattr(obj.pedido, "recalcular_pagamentos"):
            obj.pedido.recalcular_pagamentos()

    # ====== BOTÃO "RECEBER SALDO" NO PEDIDO ======
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "receber-saldo/<int:pedido_id>/",
                self.admin_site.admin_view(self.receber_saldo_view),
                name="core_receber_saldo",
            ),
        ]
        return custom + urls

    def receber_saldo_view(self, request, pedido_id):
        pedido = Pedido.objects.get(pk=pedido_id)
        saldo = _saldo(pedido)

        if saldo <= 0:
            messages.warning(request, f"Pedido {pedido.id} já está quitado.")
            return redirect(reverse("admin:core_pedido_changelist"))

        # cria pagamento “automaticamente” (método default: numerario)
        PagamentoPedido.objects.create(
            pedido=pedido,
            valor=saldo,
            metodo_pagamento="numerario",  # podes trocar para um default teu
            criado_por=Funcionario.objects.get(user=request.user),
            pago_em=timezone.now(),
        )

        if hasattr(pedido, "recalcular_pagamentos"):
            pedido.recalcular_pagamentos()

        messages.success(request, f"Recebido saldo do Pedido {pedido.id}: {saldo:.2f} MZN")
        return redirect(reverse("admin:core_pedido_change", args=[pedido.id]))

    # ====== ACTION: RECEBER SALDO DOS PEDIDOS SELECIONADOS ======
    @admin.action(description="Receber saldo dos pedidos selecionados (gera pagamento numerário)")
    def receber_saldo_pedidos_selecionados(self, request, queryset):
        """
        Esta action é chamada na lista de PagamentoPedido, mas vamos ignorar
        os pagamentos e usar os pedidos associados.
        """
        pedidos = Pedido.objects.filter(id__in=queryset.values_list("pedido_id", flat=True)).distinct()
        funcionario = Funcionario.objects.get(user=request.user)

        feitos = 0
        for pedido in pedidos:
            saldo = _saldo(pedido)
            if saldo <= 0:
                continue
            PagamentoPedido.objects.create(
                pedido=pedido,
                valor=saldo,
                metodo_pagamento="numerario",
                criado_por=funcionario,
                pago_em=timezone.now(),
            )
            if hasattr(pedido, "recalcular_pagamentos"):
                pedido.recalcular_pagamentos()
            feitos += 1

        if feitos:
            messages.success(request, f"{feitos} pedido(s) quitado(s) com pagamento do saldo.")
        else:
            messages.warning(request, "Nenhum pedido com saldo pendente.")










