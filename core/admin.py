from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from .forms import ItemPedidoForm
from .models import Lavandaria, Funcionario, ItemServico, Servico, Cliente, Pedido, ItemPedido
from django.urls import reverse
from django.utils.html import format_html
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import User, Group
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

admin.site.unregister(User)
admin.site.unregister(Group)


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
class ItemPedidoInline(TabularInline):
    model = ItemPedido
    extra = 1  # Número de linhas extras para novos itens
    fields = ('servico', 'item_de_servico', 'quantidade', 'preco_total')
    readonly_fields = ('preco_total',)  # Para evitar edições manuais


# Configuração do modelo Lavandaria no Admin
@admin.register(Lavandaria)
class LavandariaAdmin(ModelAdmin):
    list_display = ('nome', 'endereco', 'telefone', 'email', 'gerente', 'criado_em', 'atualizado_em')
    search_fields = ('nome', 'email', 'telefone')
    list_filter = ('criado_em', 'atualizado_em')
    fieldsets = (
        ('Informações Básicas', {'fields': ('nome', 'endereco', 'telefone', 'email', 'gerente')}),
        ('Datas', {'fields': ('criado_em', 'atualizado_em')}),
    )
    readonly_fields = ('criado_em', 'atualizado_em')


# Configuração do modelo Funcionario no Admin
@admin.register(Funcionario)
class FuncionarioAdmin(ModelAdmin):
    list_display = ('user', 'lavandaria', 'funcao', 'telefone')
    search_fields = ('user__username', 'telefone', 'lavandaria__nome')
    list_filter = ('funcao',)


# Configuração do modelo ItemServico no Admin
@admin.register(ItemServico)
class ItemServicoAdmin(ModelAdmin):
    list_display = ('imagem', 'nome', 'disponivel')
    search_fields = ('nome',)
    list_filter = ('disponivel',)


# Configuração do modelo Servico no Admin
@admin.register(Servico)
class ServicoAdmin(ModelAdmin):
    list_display = ('nome', 'lavandaria', 'preco_base', 'ativo')
    search_fields = ('nome', 'lavandaria__nome')
    list_filter = ('ativo', 'lavandaria')
    fieldsets = (
        ('Informações do Serviço', {'fields': ('nome', 'descricao', 'preco_base', 'ativo')}),
        ('Lavandaria', {'fields': ('lavandaria',)}),
    )


# Configuração do modelo Cliente no Admin
@admin.register(Cliente)
class ClienteAdmin(ModelAdmin):
    list_display = ('nome', 'email', 'telefone', 'endereco')
    search_fields = ('nome', 'email', 'telefone')


# Configuração do modelo Pedido no Admin
@admin.register(Pedido)
class PedidoAdmin(ModelAdmin):
    list_display = ('id', 'cliente', 'lavandaria', 'status', 'total', 'criado_em', 'atualizado_em', 'gerar_recibo_link')
    search_fields = ('cliente__nome', 'lavandaria__nome', 'status')
    list_filter = ('status', 'criado_em', 'atualizado_em')
    fieldsets = (
        ('Detalhes do Pedido', {'fields': ('cliente', 'lavandaria', 'status')}),
        ('Totais e Datas', {'fields': ('total', 'criado_em', 'atualizado_em')}),
    )
    readonly_fields = ('total', 'criado_em', 'atualizado_em')
    inlines = [ItemPedidoInline]

    def gerar_recibo_link(self, obj):
        url = reverse('gerar_recibo_pdf', args=[obj.id])
        return format_html('<a href="{}" target="_blank">Imprimir Recibo</a>', url)

    gerar_recibo_link.short_description = "Recibo"


# Configuração do modelo ItemPedido no Admin
@admin.register(ItemPedido)
class ItemPedidoAdmin(ModelAdmin):
    form = ItemPedidoForm
    list_display = ('pedido', 'servico', 'item_de_servico', 'quantidade', 'preco_total')
    search_fields = ('pedido__id', 'servico__nome', 'item_de_servico__nome')
    list_filter = ('servico',)
    readonly_fields = ('preco_total',)
