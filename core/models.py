from django.db import models
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from decimal import Decimal


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
    telefone = models.CharField(max_length=20, blank=True, null=True)
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
        return f"{self.nome} - {self.get_preco_formatado()}"

    def get_preco_formatado(self):
        """Retorna o preço formatado em Reais"""
        return f"MT: {self.preco_base:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


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
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("completo","Completo"),
        ("pronto", "Pronto"),
        ("entregue", "Entregue"),
    ]

    STATUS_PAGAMENTO_CHOICES = [
        ("nao_pago", "Não pago"),
        ("parcial", "Parcial"),
        ("pago", "Pago"),
    ]

    cliente = models.ForeignKey("Cliente", on_delete=models.CASCADE, related_name="pedidos")
    lavandaria = models.ForeignKey("Lavandaria", on_delete=models.CASCADE, related_name="pedidos")
    funcionario = models.ForeignKey(
        "Funcionario", on_delete=models.SET_NULL, related_name="pedidos", null=True, blank=True
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    criado_em = models.DateTimeField(auto_now_add=True)

    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    # LEGACY (não edite manualmente; é derivado da soma dos pagamentos)
    pago = models.BooleanField(default=False)
    data_pagamento = models.DateTimeField(null=True, blank=True)

    # NOVO
    status_pagamento = models.CharField(
        max_length=20, choices=STATUS_PAGAMENTO_CHOICES, default="nao_pago"
    )
    total_pago = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    @property
    def saldo(self) -> Decimal:
        return (self.total or Decimal("0.00")) - (self.total_pago or Decimal("0.00"))

    def clean(self):
        # valida fluxo operacional (igual ao teu, só mais compacto)
        if self.pk:
            pedido_original = Pedido.objects.get(pk=self.pk)
            status_original = pedido_original.status
            status_novo = self.status

            transicoes = {
                "pendente": ["completo"],
                "completo": ["pronto"],
                "pronto": ["entregue"],
                "entregue": [],
            }
            if status_novo != status_original and status_novo not in transicoes.get(status_original, []):
                raise ValidationError(
                    {"status": f"Transição inválida: {status_original} → {status_novo}"}
                )

        if self.total is not None and self.total < 0:
            raise ValidationError({"total": "O total não pode ser negativo."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def atualizar_total(self):
        self.total = sum((item.preco_total or 0) for item in self.itens.all())
        self.save(update_fields=["total"])
        self.recalcular_pagamentos()

    def recalcular_pagamentos(self):
        if not self.pk:
            return

        soma = self.pagamentos.aggregate(s=Sum("valor"))["s"] or Decimal("0.00")
        soma = Decimal(soma)
        self.total_pago = soma

        if soma <= 0:
            self.status_pagamento = "nao_pago"
            self.pago = False
            self.data_pagamento = None
        elif soma < (self.total or Decimal("0.00")):
            self.status_pagamento = "parcial"
            self.pago = False
            ultimo = self.pagamentos.order_by("-pago_em").first()
            self.data_pagamento = ultimo.pago_em if ultimo else self.data_pagamento
        else:
            self.status_pagamento = "pago"
            self.pago = True
            ultimo = self.pagamentos.order_by("-pago_em").first()
            self.data_pagamento = ultimo.pago_em if ultimo else timezone.now()

        self.save(update_fields=["total_pago", "status_pagamento", "pago", "data_pagamento"])

    @transaction.atomic
    def registrar_pagamento(self, *, valor, metodo_pagamento, funcionario=None, referencia=None):
        valor = Decimal(valor)
        if valor <= 0:
            raise ValidationError("Valor do pagamento deve ser > 0.")

        pedido = Pedido.objects.select_for_update().get(pk=self.pk)

        pago_ate_agora = pedido.pagamentos.aggregate(s=Sum("valor"))["s"] or Decimal("0.00")
        pago_ate_agora = Decimal(pago_ate_agora)

        saldo = (pedido.total or Decimal("0.00")) - pago_ate_agora
        if valor > saldo:
            raise ValidationError(f"Pagamento excede o saldo. Saldo atual: {saldo}")

        PagamentoPedido.objects.create(
            pedido=pedido,
            valor=valor,
            metodo_pagamento=metodo_pagamento,
            referencia=referencia,
            criado_por=funcionario,
        )

        pedido.recalcular_pagamentos()
        return pedido

    def __str__(self):
        return f"Pedido {self.id} - {self.cliente} - {self.get_status_display()}"

    class Meta:
        ordering = ["-criado_em"]


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
    descricao = models.TextField(blank=True, null=True)

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


class PagamentoPedido(models.Model):

    METODO_PAGAMENTO_CHOICES = [
        ('numerario', 'Numerario'),
        ('pos', 'POS (Cartao)'),
        ('conta_movel', 'Conta Movel'),
        ('mpesa', 'M-Pesa'),
        ('emola', 'e-Mola'),
        ('outro', 'Outro'),
    ]

    pedido = models.ForeignKey("Pedido", on_delete=models.CASCADE, related_name="pagamentos")
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pagamento = models.CharField(max_length=20, choices=METODO_PAGAMENTO_CHOICES)
    referencia = models.CharField(max_length=80, blank=True, null=True)
    pago_em = models.DateTimeField(default=timezone.now)
    criado_por = models.ForeignKey("Funcionario", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-pago_em"]

    def clean(self):
        if self.valor is None or self.valor <= 0:
            raise ValidationError({"valor": "Pagamento deve ser maior que 0."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Pagamento {self.id} - Pedido {self.pedido_id} - {self.valor}"


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
            "add_pagamentopedido", "change_pagamentopedido", "delete_pagamentopedido", "view_pagamentopedido",
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


class Recibo(models.Model):
    """
    Recibo passa a ser por pagamento (não por pedido).
    Isso evita quebrar pagamentos parciais.
    """
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="recibos")
    pagamento = models.OneToOneField(PagamentoPedido, on_delete=models.PROTECT, related_name="recibo")

    total_pago = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pagamento = models.CharField(max_length=20, choices=PagamentoPedido.METODO_PAGAMENTO_CHOICES)

    emitido_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey("Funcionario", on_delete=models.SET_NULL, blank=True, null=True)

    def save(self, *args, **kwargs):
        # NÃO mexe em status/pago aqui.
        # Status do Pedido é operacional (pendente/pronto/entregue) e pagamento é derivado dos pagamentos.
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Recibo {self.id} - Pedido {self.pedido_id} - Total: {self.total_pago}"


