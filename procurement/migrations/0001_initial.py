from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='PurchaseOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, verbose_name='Bezeichnung')),
                ('company', models.CharField(blank=True, max_length=255, verbose_name='Firma')),
                ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Preis (€)')),
                ('tool_type', models.CharField(blank=True, choices=[('sensor', 'Sensor'), ('actuator', 'Aktor'), ('tool', 'Werkzeug'), ('it', 'IT / Elektronik'), ('furniture', 'Möbel'), ('other', 'Sonstiges')], default='other', max_length=20, verbose_name='Typ')),
                ('key_specs', models.TextField(blank=True, help_text='Kurze Stichpunktliste, z. B. aus dem Datenblatt.', verbose_name='Kurzbeschreibung / Kenndaten')),
                ('purchase_date', models.DateField(blank=True, null=True, verbose_name='Kaufdatum')),
                ('project', models.CharField(blank=True, max_length=200, verbose_name='Projekt')),
                ('source_folder', models.CharField(help_text='Pfad relativ zum Basisordner, dient als eindeutiger Schlüssel für den Sync.', max_length=500, unique=True, verbose_name='Quellordner')),
                ('datasheet_path', models.CharField(blank=True, help_text='Pfad relativ zum Basisordner.', max_length=500, verbose_name='Datenblatt')),
                ('manually_verified', models.BooleanField(default=False, help_text='Wenn gesetzt, überschreibt der monatliche Sync die Fachfelder nicht mehr.', verbose_name='Manuell geprüft')),
                ('is_missing', models.BooleanField(default=False, help_text='Der Quellordner wurde beim letzten Sync nicht mehr gefunden.', verbose_name='Ordner fehlt')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Erstellt am')),
                ('last_synced', models.DateTimeField(blank=True, null=True, verbose_name='Zuletzt synchronisiert')),
            ],
            options={
                'verbose_name': 'Bestellung',
                'verbose_name_plural': 'Bestellungen',
                'ordering': ['-purchase_date', 'name'],
            },
        ),
    ]
