import pytest

from API.models import Wordform
from tests.conftest import migrate_and_import


@pytest.mark.django_db
def test_import_xml_common_analysis_definition_merge(shared_datadir):
    migrate_and_import(shared_datadir / "crkeng-common-analysis-definition-merge")

    query_set = Wordform.objects.filter(text="nipa")

    kill_him_inflections = []
    for inflection in query_set:
        for definition in inflection.definitions.all():
            if "Kill" in definition.text:
                kill_him_inflections.append(inflection)

    assert len(kill_him_inflections) == 1
    kill_him_inflection = kill_him_inflections[0]
    assert kill_him_inflection.pos == "V"


@pytest.mark.django_db
def test_import_pipon_of_different_word_classes(shared_datadir):
    # https://github.com/UAlbertaALTLab/cree-intelligent-dictionary/issues/190
    # Issue description: search results for some inflected form of word pipon is not showing up
    # Cause: pipon lemmas wrongly marked as "as-is" in the database when the xml actually provided enough resolution
    # on the word classes (VII and NI)

    # The Cree word pipon has two entries in the test xml, one's word class is VII and the other's is NI
    migrate_and_import(shared_datadir / "crkeng-pipon-of-different-word-classes")

    # todo: let `migrate_and_import` report success/ambiguity/no-analysis count so that further tests to the importer
    #   can be easier constructed. e.g. in this case we'll only need to assert `success == 2`

    assert (
        Wordform.objects.filter(text="pipon", is_lemma=True, as_is=False).count() == 2
    )
