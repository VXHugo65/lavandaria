from django.db import migrations


SQL = """
-- 1) Garante colunas novas no core_pedido (não destrutivo)
ALTER TABLE core_pedido
    ADD COLUMN IF NOT EXISTS status_pagamento VARCHAR(20);

ALTER TABLE core_pedido
    ADD COLUMN IF NOT EXISTS total_pago NUMERIC(10,2) NOT NULL DEFAULT 0;

-- 2) Backfill total_pago a partir de core_pagamentopedido (se existir)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'core_pagamentopedido'
    ) THEN
        UPDATE core_pedido p
        SET total_pago = COALESCE((
            SELECT SUM(pp.valor)
            FROM core_pagamentopedido pp
            WHERE pp.pedido_id = p.id
        ), 0);
    ELSE
        -- Se não existir a tabela de pagamentos, mantém total_pago=0 (default)
        UPDATE core_pedido SET total_pago = COALESCE(total_pago, 0);
    END IF;
END $$;

-- 3) Backfill status_pagamento coerente com total / total_pago
UPDATE core_pedido
SET status_pagamento = CASE
    WHEN COALESCE(total_pago, 0) >= COALESCE(total, 0) AND COALESCE(total, 0) > 0 THEN 'pago'
    WHEN COALESCE(total_pago, 0) > 0 THEN 'parcial'
    ELSE 'aberto'
END
WHERE status_pagamento IS NULL OR status_pagamento = '';

-- 4) (Opcional) Sincroniza o boolean pago sem destruir histórico
-- Só marca como TRUE quando estiver quitado.
UPDATE core_pedido
SET pago = TRUE
WHERE status_pagamento = 'pago' AND pago = FALSE;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_alter_pedido_options_remove_pedido_metodo_pagamento_and_more"),
    ]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=migrations.RunSQL.noop),
    ]
