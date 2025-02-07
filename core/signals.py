from django.db.models.signals import post_migrate
from django.dispatch import receiver
from .models import criar_grupos_com_permissoes


@receiver(post_migrate)
def criar_grupos_apos_migracao(sender, **kwargs):
    criar_grupos_com_permissoes()
