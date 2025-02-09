from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline, StackedInline
from .models import Lavandaria, ItemServico, Servico, Cliente, Pedido, ItemPedido, Funcionario
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
from unfold.contrib.import_export.forms import ExportForm, ImportForm, SelectableFieldsExportForm

admin.site.unregister(Group)
admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    # Forms loaded from `unfold.forms`
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


# Inline para gerenciar os itens de pedido diretamente no pedido
class ItemPedidoInline(StackedInline):
    model = ItemPedido
    extra = 0  # Número de linhas extras para novos itens
    fields = [
        ('item_de_servico',),  # Primeira linha
        ('descricao', 'quantidade', 'preco_total'),   # Segunda linha
    ]
    autocomplete_fields = ('item_de_servico',)
    readonly_fields = ('preco_total',)


# Configuração do modelo Lavandaria no Admin
@admin.register(Lavandaria)
class LavandariaAdmin(ModelAdmin):
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
    list_display = ('nome', 'telefone', 'endereco')
    search_fields = ('nome', 'telefone')


# Configuração do modelo Funcionario no Admin
@admin.register(Funcionario)
class FuncionarioAdmin(ModelAdmin):
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


# Configuração do modelo Pedido no Admin
API_URL = 'http://api.mozesms.com/bulk_json/v2/'
BEARER_TOKEN = 'Bearer 2309:fI1aPs-MCF2CJ-nKkMQD-61cLGv'
SENDER = "ESHOP"


def enviar_sms_mozesms(numero, mensagem):
    """
    Envia um SMS usando a API Mozesms.
    """
    payload = {
        'sender': 'ESHOP',
        'messages': [{
            'number': numero,
            'text': mensagem,
            'from': SENDER
        }]
    }
    headers = {'Authorization': BEARER_TOKEN}

    try:
        response = requests.post(API_URL, json=payload, headers=headers)

        if response.status_code == 200:
            try:
                # Carregar a resposta JSON (primeira parte)
                json_resposta = json.loads(response.text.split('}{')[0] + '}')

                # Verificar sucesso na resposta
                if json_resposta.get('success') and json_resposta.get('result', {}).get('success'):
                    print("SMS enviado com sucesso!")
                    return True
                else:
                    print("Erro ao enviar SMS:", json_resposta)
                    return False

            except Exception as e:
                print(f"Erro ao processar a resposta JSON: {e}")
                return False
        else:
            print(f"Erro na requisição: {response.status_code}")
            return False

    except requests.RequestException as e:
        print(f"Erro ao enviar SMS: {e}")
        return False


@admin.register(Pedido)
class PedidoAdmin(ModelAdmin):
    list_display = ('id', 'cliente', 'criado_em', 'status', 'pago', 'total', 'botao_imprimir')
    search_fields = ('cliente__nome', 'id')
    list_display_links = ('cliente', 'id')
    list_editable = ('status', 'pago')
    list_filter = ('status', 'criado_em', 'pago')
    fieldsets = (
        ('Detalhes do Pedido', {'fields': ('cliente', 'lavandaria', 'funcionario', 'status',)}),
        ('Totais e Datas', {'fields': ('total', 'criado_em')}),
        ('', {'fields': ('pago', 'metodo_pagamento')}),
    )
    readonly_fields = ('total', 'criado_em', 'funcionario', 'lavandaria')
    autocomplete_fields = ('cliente',)
    inlines = [ItemPedidoInline]

    def save_model(self, request, obj, form, change):
        try:
            # Obtém o funcionário associado ao usuário logado
            funcionario = Funcionario.objects.get(user=request.user)
            obj.funcionario = funcionario

            # Verifica se o funcionário tem uma lavandaria associada
            if funcionario.lavandaria:
                obj.lavandaria = funcionario.lavandaria
            else:
                raise ValueError("O funcionário logado não está associado a nenhuma lavandaria.")
        except Funcionario.DoesNotExist:
            raise ValueError("O usuário logado não está associado a nenhum funcionário.")

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

    def enviar_sms_pedido_pronto(self, request, queryset):
        pedidos_notificados = 0

        for pedido in queryset:
            if pedido.status == 'pronto' and hasattr(pedido.cliente, 'telefone'):
                mensagem = f"Olá {pedido.cliente.nome}, seu pedido #{pedido.id} está pronto para retirada na lavandaria {pedido.lavandaria.nome}."
                resposta = enviar_sms_mozesms(pedido.cliente.telefone, mensagem)

                if resposta:
                    pedidos_notificados += 1

        if pedidos_notificados:
            messages.success(request, f"Mensagem enviada com sucesso para {pedidos_notificados} clientes.")
        else:
            messages.warning(request,
                             "ERRO. Verifique se os pedidos estão 'prontos' e se os clientes têm número de telefone.")

    actions = [enviar_sms_pedido_pronto]

    enviar_sms_pedido_pronto.short_description = "Enviar mensagem de pedido pronto"


# Configuração do modelo ItemPedido no Admin
@admin.register(ItemPedido)
class ItemPedidoAdmin(ModelAdmin):
    list_display = ('pedido', 'item_de_servico', 'quantidade', 'preco_total')
    search_fields = ('pedido__id', 'item_de_servico__nome')
    list_filter = ('servico',)
    readonly_fields = ('preco_total',)
    autocomplete_fields = ('item_de_servico',)
