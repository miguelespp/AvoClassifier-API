from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("classifications", "0002_update_disease_categories"),
    ]

    operations = [
        # Renombrar registros existentes con valor 'pudricion' → 'sarna'
        migrations.RunSQL(
            sql="UPDATE classifications_classification SET predicted_category = 'sarna' WHERE predicted_category = 'pudricion';",
            reverse_sql="UPDATE classifications_classification SET predicted_category = 'pudricion' WHERE predicted_category = 'sarna';",
        ),
        # Actualizar los choices del campo
        migrations.AlterField(
            model_name="classification",
            name="predicted_category",
            field=models.CharField(
                blank=True,
                choices=[
                    ("saludable", "Saludable"),
                    ("antracnosis", "Antracnosis"),
                    ("sarna", "Sarna"),
                ],
                max_length=30,
            ),
        ),
    ]
