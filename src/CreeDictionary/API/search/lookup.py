from __future__ import annotations

import logging
from typing import Iterable

from django.db.models import Q

from CreeDictionary.utils import (
    get_modified_distance,
)
from CreeDictionary.utils.english_keyword_extraction import stem_keywords
from morphodict.analysis import (
    strict_generator,
    rich_analyze_relaxed,
)
from morphodict.lexicon.models import Wordform, SourceLanguageKeyword
from . import core
from .types import Result
from ...utils.cree_lev_dist import remove_cree_diacritics

logger = logging.getLogger(__name__)


def fetch_results(search_run: core.SearchRun):
    """
    The rest of this method is code Eddie has NOT refactored, so I don't really
    understand what's going on here:
    """

    fetch_results_from_keywords(search_run)

    # Use the spelling relaxation to try to decipher the query
    #   e.g., "atchakosuk" becomes "acâhkos+N+A+Pl" --
    #         thus, we can match "acâhkos" in the dictionary!
    fst_analyses = rich_analyze_relaxed(search_run.internal_query)

    db_matches = list(
        Wordform.objects.filter(raw_analysis__in=[a.tuple for a in fst_analyses])
    )

    for wf in db_matches:
        search_run.add_result(
            Result(
                wf,
                source_language_match=wf.text,
                query_wordform_edit_distance=get_modified_distance(
                    wf.text, search_run.internal_query
                ),
            )
        )

        # An exact match here means we’re done with this analysis.
        assert wf.analysis in fst_analyses, "wordform analysis not in search set"
        fst_analyses.remove(wf.analysis)

    # fst_analyses has now been thinned by calls to `fst_analyses.remove()`
    # above; remaining items are analyses which are not in the database,
    # although their lemmas should be.
    for analysis in fst_analyses:
        # When the user query is outside of paradigm tables
        # e.g. mad preverb and reduplication: ê-mâh-misi-nâh-nôcihikocik
        # e.g. Initial change: nêpât: {'IC+nipâw+V+AI+Cnj+3Sg'}

        normatized_form_for_analysis = strict_generator().lookup(analysis.smushed())
        if len(normatized_form_for_analysis) == 0:
            logger.error(
                "Cannot generate normative form for analysis: %s (query: %s)",
                analysis,
                search_run.internal_query,
            )
            continue

        # If there are multiple forms for this analysis, use the one that is
        # closest to what the user typed.
        normatized_user_query = min(
            normatized_form_for_analysis,
            key=lambda f: get_modified_distance(f, search_run.internal_query),
        )

        possible_lemma_wordforms = Wordform.objects.filter(
            text=analysis.lemma, is_lemma=True
        )[:]

        if len(possible_lemma_wordforms) > 1:
            max_tag_intersection_count = max(
                analysis.tag_intersection_count(lwf.analysis)
                for lwf in possible_lemma_wordforms
            )
            print(f"{max_tag_intersection_count=}")
            possible_lemma_wordforms = [
                lwf
                for lwf in possible_lemma_wordforms
                if analysis.tag_intersection_count(lwf.analysis)
                == max_tag_intersection_count
            ]

        for lemma_wordform in possible_lemma_wordforms:
            synthetic_wordform = Wordform(
                text=normatized_user_query,
                raw_analysis=analysis.tuple,
                lemma=lemma_wordform,
            )
            search_run.add_result(
                Result(
                    synthetic_wordform,
                    pronoun_as_is_match=True,
                    query_wordform_edit_distance=get_modified_distance(
                        search_run.internal_query,
                        normatized_user_query,
                    ),
                )
            )

    res = SourceLanguageKeyword.objects.filter(
        Q(text=search_run.internal_query)
        | Q(text=remove_cree_diacritics(search_run.internal_query).lower())
    )
    for kw in res:
        search_run.add_result(
            Result(
                kw.wordform,
                source_language_keyword_match=[kw.text],
                query_wordform_edit_distance=get_modified_distance(
                    search_run.internal_query, kw.wordform.text
                ),
            )
        )


def fetch_results_from_keywords(search_run):
    # now we get results searched by English
    for stemmed_keyword in stem_keywords(search_run.internal_query):
        for wordform in Wordform.objects.filter(
            target_language_keyword__text__iexact=stemmed_keyword
        ):
            search_run.add_result(
                Result(wordform, target_language_keyword_match=[stemmed_keyword])
            )


def filter_cw_wordforms(queryset: Iterable[Wordform]) -> Iterable[Wordform]:
    """
    return the wordforms that has definition from CW dictionary

    :param queryset: an Iterable of Wordforms
    """
    for wordform in queryset:
        for definition in wordform.definitions.all():
            if "CW" in definition.source_ids:
                yield wordform
                break
