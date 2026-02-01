from django.contrib import admin
from unfold.admin import ModelAdmin, StackedInline
from .models import Lavandaria, ItemServico, Servico, Cliente, Pedido, ItemPedido, Funcionario, Recibo
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
from collections import defaultdict
from django.utils import timezone

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


def gerar_relatorio_financeiro(modeladmin, request, queryset):
    """
    Gera um relatório financeiro em PDF dos pedidos selecionados no Django Admin.
    """

    # Separar pagos e não pagos
    queryset_pagos = queryset.filter(pago=True).order_by('metodo_pagamento')
    queryset_nao_pagos = queryset.filter(pago=False)

    # Calcular totais por pedido (pagos)
    for pedido in queryset_pagos:
        pedido.total_quantidade = sum(item.quantidade for item in pedido.itens.all())
        pedido.total_valor = sum(item.preco_total for item in pedido.itens.all())

    # Calcular totais por pedido (não pagos)
    for pedido in queryset_nao_pagos:
        pedido.total_valor = sum(item.preco_total for item in pedido.itens.all())

    # Totais gerais
    total_quantidade = sum(pedido.total_quantidade for pedido in queryset_pagos)
    total_valor = sum(pedido.total_valor for pedido in queryset_pagos)

    # Datas do relatório
    if queryset.exists():
        start_date = queryset.order_by('data_pagamento').first().data_pagamento.strftime('%d/%m/%Y')
        end_date = queryset.order_by('data_pagamento').last().data_pagamento.strftime('%d/%m/%Y')
    else:
        start_date = end_date = datetime.today().strftime('%d/%m/%Y')

    lavandaria = request.user.funcionario.lavandaria

    # Renderizar o HTML para PDF
    html_string = render_to_string('core/relatorio_financeiro.html', {
        'lavandaria': lavandaria,
        'pedidos_pagos': queryset_pagos,
        'nao_pagos': [],
        'total_quantidade': total_quantidade,
        'total_valor': total_valor,
        'start_date': start_date,
        'end_date': end_date,
    })

    # Gerar o PDF
    buffer = BytesIO()
    filename = f"relatorio_financeiro_{start_date}_a_{end_date}.pdf"
    pisa_status = pisa.CreatePDF(html_string, dest=buffer)

    if pisa_status.err:
        return HttpResponse("Erro ao gerar PDF", content_type="text/plain")

    buffer.seek(0)
    response = HttpResponse(buffer, content_type="application/pdf")
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

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

    def get_readonly_fields(self, request, obj=None):
        """
        Torna todos os campos readonly exceto 'descricao' quando o pedido já foi criado.
        """
        if obj and obj.pk:  # Se o pedido já existe no banco
            # Pega todos os campos do modelo
            all_fields = [field.name for field in self.model._meta.fields]
            # Remove 'descricao' da lista de campos readonly
            readonly_fields = [field for field in all_fields if field != 'descricao']
            # Adiciona os campos readonly padrão
            readonly_fields.extend(self.readonly_fields)
            return readonly_fields
        return self.readonly_fields

    def has_add_permission(self, request, obj=None):
        """
        Impede adicionar novos itens se o pedido já foi criado.
        """
        if obj and obj.pk:
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        """
        Impede deletar itens se o pedido já foi criado.
        """
        if obj and obj.pk:
            return False
        return super().has_delete_permission(request, obj)



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
    list_display = ('id', 'cliente', 'criado_em', 'data_pagamento', 'status', 'pago', 'total', 'botao_imprimir')
    search_fields = ('cliente__nome', 'cliente__telefone', 'id')
    list_display_links = ('cliente', 'id')
    list_editable = ('pago',)  # Remove status da list_editable para evitar mudanças diretas
    list_filter = (
        'status', 'pago', ("data_pagamento", RangeDateTimeFilter), 'metodo_pagamento',
        ("criado_em", RangeDateTimeFilter)
    )
    list_filter_submit = True
    fieldsets = (
        ('Detalhes do Pedido', {'fields': ('cliente', 'lavandaria', 'funcionario', 'status',)}),
        ('Totais e Datas', {'fields': ('total', 'criado_em')}),
        ('', {'fields': ('pago', 'metodo_pagamento')}),
    )
    readonly_fields = ('criado_em', 'funcionario', 'lavandaria')
    autocomplete_fields = ('cliente',)
    inlines = [ItemPedidoInline]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        if obj and obj.pk:
            self._restrict_status_choices(form, obj)

        return form

    def _restrict_status_choices(self, form, obj):
        """Restringe as choices do status baseado no estado atual"""
        if 'status' in form.base_fields:
            current_status = obj.status

            # CORREÇÃO: Fluxo sequencial estrito
            status_flow = {
                'pendente': ['pendente', 'pronto'],  # Pendente só pode ir para Pronto
                'pronto': ['pronto', 'entregue'],  # Pronto só pode ir para Entregue
                'entregue': ['entregue']  # Entregue não pode mudar
            }

            allowed_statuses = status_flow.get(current_status, [current_status])
            choices = [choice for choice in form.base_fields['status'].choices
                       if choice[0] in allowed_statuses]

            form.base_fields['status'].choices = choices

            # Se só tem uma opção, desabilita o campo
            if len(allowed_statuses) == 1:
                form.base_fields['status'].disabled = True

    def save_model(self, request, obj, form, change):
        if change and obj.pk:
            # Obtém o estado anterior do pedido
            try:
                original_status = Pedido.objects.get(pk=obj.pk).status
                new_status = form.cleaned_data.get('status')

                # CORREÇÃO: Transições válidas estritamente sequenciais
                valid_transitions = {
                    'pendente': ['pronto'],  # Pendente → Pronto (apenas)
                    'pronto': ['entregue'],  # Pronto → Entregue (apenas)
                    'entregue': []  # Entregue → Nada (não pode mudar)
                }

                if new_status != original_status:
                    if new_status not in valid_transitions.get(original_status, []):
                        messages.error(
                            request,
                            f"Não é possível alterar o status de '{original_status}' para '{new_status}'. "
                            f"Transição permitida: {', '.join(valid_transitions[original_status]) or 'Nenhuma'}"
                        )
                        # Restaura o status original
                        obj.status = original_status
                        return  # Impede a mudança de status inválida

            except Pedido.DoesNotExist:
                pass  # Pedido novo, não precisa validar

        # Resto do save_model original
        try:
            funcionario = Funcionario.objects.get(user=request.user)
            obj.funcionario = funcionario

            if funcionario.lavandaria:
                obj.lavandaria = funcionario.lavandaria
            else:
                raise ValueError("O funcionário logado não está associado a nenhuma lavandaria.")
        except Funcionario.DoesNotExist:
            raise ValueError("O usuário logado não está associado a nenhum funcionário.")

        if form.cleaned_data.get('pago') and not obj.data_pagamento:
            obj.data_pagamento = timezone.now()

        super(PedidoAdmin, self).save_model(request, obj, form, change)

    def get_queryset(self, request):
        qs = super(PedidoAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return qs

        try:
            # Obtém o funcionário associado ao usuário logado
            funcionario = Funcionario.objects.get(user=request.user)

            # Garante que o funcionário tenha uma lavandaria
            if funcionario.lavandaria:
                return qs.filter(lavandaria=funcionario.lavandaria)
            else:
                raise ValueError("O funcionário logado não está associado a nenhuma lavandaria.")
        except Funcionario.DoesNotExist:
            raise ValueError("O usuário logado não está associado a nenhum funcionário.")

    def botao_imprimir(self, obj):
        url = reverse('core:imprimir_recibo_imagem', args=[obj.id])
        return format_html(f'<a class="button" href="{url}" target="_blank">Imprimir</a>')

    botao_imprimir.short_description = "Imprimir Recibo"

    # Ações customizadas para avançar status de forma controlada
    def marcar_como_pronto(self, request, queryset):
        """Marca pedidos selecionados como pronto (apenas se estiverem pendentes)"""
        pedidos_processados = 0
        for pedido in queryset:
            if pedido.status == 'pendente':
                pedido.status = 'pronto'
                pedido.save()
                pedidos_processados += 1
            else:
                messages.warning(
                    request,
                    f"Pedido {pedido.id} não pode ser marcado como pronto. Status atual: {pedido.status}"
                )

        if pedidos_processados:
            messages.success(request, f"{pedidos_processados} pedidos marcados como pronto.")
        else:
            messages.warning(request, "Nenhum pedido pôde ser processado.")

    def marcar_como_entregue(self, request, queryset):
        """Marca pedidos selecionados como entregue (apenas se estiverem prontos)"""
        pedidos_processados = 0
        for pedido in queryset:
            if pedido.status == 'pronto':
                pedido.status = 'entregue'
                pedido.save()
                pedidos_processados += 1
            else:
                messages.warning(
                    request,
                    f"Pedido {pedido.id} não pode ser marcado como entregue. Status atual: {pedido.status}"
                )

        if pedidos_processados:
            messages.success(request, f"{pedidos_processados} pedidos marcados como entregue.")
        else:
            messages.warning(request, "Nenhum pedido pôde ser processado.")

    marcar_como_pronto.short_description = "Marcar como Pronto (apenas pendentes)"
    marcar_como_entregue.short_description = "Marcar como Entregue (apens prontos)"

 

    def enviar_sms_pedido_pronto(self, request, queryset):
        for pedido in queryset:
            if pedido.status != 'pronto':
                self.message_user(
                    request,
                    "❌ ERRO. Verifique se os pedidos estão 'prontos'.",
                    level=messages.ERROR
                )
                return
    
            if not pedido.cliente.telefone:
                self.message_user(
                    request,
                    "❌ ERRO. O cliente não tem número de telefone.",
                    level=messages.ERROR
                )
                return
    
            mensagem = (
                f"Olá {pedido.cliente.nome}, "
                f"o seu artigo #{pedido.id} está pronto, para o levantamento. "
                f"Para mais info. Clique aqui "
                f"https://lavandaria-production.up.railway.app/meu-pedido/{pedido.id}"
            )
    
            telefone = pedido.cliente.telefone
            # enviar_sms(telefone, mensagem)
    
        self.message_user(
            request,
            "✅ SMS enviado com sucesso."
        )


    # Atualiza as actions para incluir as novas funções
    actions = [
        marcar_como_pronto,
        marcar_como_entregue,
        enviar_sms_pedido_pronto,
        gerar_relatorio_pdf,
        gerar_relatorio_financeiro
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





















