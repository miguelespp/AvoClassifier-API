"""
Migration: 0002_update_disease_categories

Changes:
  - DiseaseCategory choices: category_a/b/c → saludable / antracnosis / pudricion
  - predicted_category max_length: 20 → 30  (necesario por 'antracnosis' = 11 chars,
    no estrictamente requerido, pero se amplía por consistencia con el modelo)
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("classifications", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="classification",
            name="predicted_category",
            field=models.CharField(
                blank=True,
                choices=[
                    ("saludable", "Saludable"),
                    ("antracnosis", "Antracnosis"),
                    ("pudricion", "Pudrición Radicular"),
                ],
                max_length=30,
            ),
        ),
    ]
