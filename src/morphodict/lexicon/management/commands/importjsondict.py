import json
from argparse import ArgumentParser
from pathlib import Path

from django.core.management import BaseCommand

from morphodict.lexicon.models import Wordform


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser):
        parser.add_argument("json_file")

    def handle(self, json_file, **options):
        data = json.loads(Path(json_file).read_text())
        for entry in data:
            Wordform.objects.create(
                text=entry["head"],
                analysis=entry.get("analysis", None),
                paradigm=entry.get("paradigm", None),
                slug=entry["slug"],
            )
