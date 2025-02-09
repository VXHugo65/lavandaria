from django.db import models
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType


# Modelo para Lavandarias
class Lavandaria(models.Model):
    """
    Representa uma lavandaria cadastrada no sistema.
    """
    nome = models.CharField(max_length=255)
    endereco = models.TextField()
    telefone = models.CharField(max_length=20, unique=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome


# Modelo para Funcionários
class Funcionario(models.Model):
    """
    Representa um funcionário associado a uma lavandaria.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='funcionario')
    lavandaria = models.ForeignKey(Lavandaria, on_delete=models.CASCADE, related_name='funcionarios')
    telefone = models.CharField(max_length=20, unique=True)
    grupo = models.CharField(
        max_length=255,
        choices=[('gerente', 'Gerente'), ('caixa', 'Caixa')],
        help_text="Define o grupo do usuário."
    )

    def __str__(self):
        return f"{self.user.username} - {self.grupo}"

    def save(self, *args, **kwargs):
        criar_grupos_com_permissoes()
        super().save(*args, **kwargs)

        # Associa o usuário ao grupo correto
        if self.grupo:
            grupo = Group.objects.get(name=self.grupo)
            self.user.groups.set([grupo])

        self.user.is_staff = True
        self.user.save()


# Modelo para Tipos de Artigos (Itens de Serviço)
class ItemServico(models.Model):
    """
    Representa um tipo de artigo disponível para serviço.
    """
    nome = models.CharField(max_length=255)
    preco_base = models.DecimalField(max_digits=10, decimal_places=2)
    disponivel = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Artigo"  # Nome no singular
        verbose_name_plural = "Artigos"  # Nome no plural

    def __str__(self):
        return self.nome


# Modelo para Serviços disponíveis na Lavandaria
class Servico(models.Model):
    """
    Representa um serviço oferecido por uma lavandaria.
    """
    lavandaria = models.ForeignKey(Lavandaria, on_delete=models.CASCADE, related_name='servicos')
    nome = models.CharField(max_length=255)
    descricao = models.TextField(blank=True, null=True)
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nome}"


# Modelo para Clientes
class Cliente(models.Model):
    """
    Representa um cliente do sistema.
    """
    nome = models.CharField(max_length=255)
    telefone = models.CharField(max_length=20, null=True, blank=True)
    endereco = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.nome} - {self.telefone}"


# Modelo para Pedidos
class Pedido(models.Model):
    """
    Representa um pedido associado a uma lavandaria e cliente.
    """
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('pronto', 'Pronto'),
        ('entregue', 'Entregue'),
    ]
    METODO_PAGAMENTO_CHOICES = [
        ('numerario', 'Numerário'),
        ('pos', 'POS (Cartão)'),
        ('conta_movel', 'Conta Movel'),
        ('mpesa', 'M-Pesa'),
        ('emola', 'e-Mola'),
        ('outro', 'Outro'),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='pedidos')
    lavandaria = models.ForeignKey(Lavandaria, on_delete=models.CASCADE, related_name='pedidos')
    funcionario = models.ForeignKey(Funcionario, on_delete=models.SET_NULL, related_name='pedidos', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    criado_em = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    pago = models.BooleanField(default=False)
    metodo_pagamento = models.CharField(max_length=20, choices=METODO_PAGAMENTO_CHOICES)

    def atualizar_total(self):
        self.total = sum(item.preco_total for item in self.itens.all())
        self.save()

    def __str__(self):
        return f"Pedido {self.id} - {self.cliente}"


# Modelo para Itens do Pedido
class ItemPedido(models.Model):
    """
    Representa um item incluído em um pedido.
    """

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='itens')
    servico = models.ForeignKey(Servico, on_delete=models.SET_NULL, related_name='itens', null=True, blank=True)
    item_de_servico = models.ForeignKey(ItemServico, on_delete=models.SET_NULL, related_name='itens', null=True, blank=True, verbose_name='Artigo')
    quantidade = models.PositiveIntegerField()
    preco_total = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    descricao = models.CharField(max_length=255, blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.item_de_servico and self.quantidade:
            self.preco_total = self.item_de_servico.preco_base * self.quantidade
        else:
            self.preco_total = 0
        super().save(*args, **kwargs)
        self.pedido.atualizar_total()

    def delete(self, *args, **kwargs):
        pedido = self.pedido
        super().delete(*args, **kwargs)
        pedido.atualizar_total()

    def __str__(self):
        item_nome = self.item_de_servico.nome if self.item_de_servico else "Item Desconhecido"
        return f"{item_nome} - {self.quantidade}x - Total: {self.preco_total}"


# Função para criar grupos e associar permissões
def criar_grupos_com_permissoes():
    """
    Cria grupos predefinidos (gerente, caixa) e associa as permissões específicas.
    """
    grupos_permissoes = {
        "gerente": [
            "view_funcionario",
            "add_itemservico", "change_itemservico", "delete_itemservico", "view_itemservico",
            "add_servico", "change_servico", "delete_servico", "view_servico",
            "add_pedido", "change_pedido", "delete_pedido", "view_pedido",
            "add_cliente", "change_cliente", "delete_cliente", "view_cliente",
            "add_itempedido", "change_itempedido", "delete_itempedido", "view_itempedido",
        ],
        "caixa": [
            "add_pedido", "change_pedido", "delete_pedido", "view_pedido",
            "add_cliente", "change_cliente", "delete_cliente", "view_cliente",
            "add_itempedido", "change_itempedido", "delete_itempedido", "view_itempedido",
        ],
    }

    for grupo_nome, permissoes_codigos in grupos_permissoes.items():
        grupo, criado = Group.objects.get_or_create(name=grupo_nome)
        if criado:
            print(f"Grupo '{grupo_nome}' criado.")

        for permissao_codigo in permissoes_codigos:
            permissao = Permission.objects.filter(codename=permissao_codigo).first()
            if permissao:
                grupo.permissions.add(permissao)

        print(f"Permissões associadas ao grupo '{grupo_nome}': {permissoes_codigos}")
