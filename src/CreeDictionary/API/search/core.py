from typing import Any, Iterable

from django.db.models import prefetch_related_objects

from . import types, presentation
from .query import Query
from .util import first_non_none_value
from ..models import WordformKey, Wordform


class SearchRun:
    """
    Holds a query and gathers results into a result collection.

    This class does not directly perform searches; for that, see runner.py.
    Instead, it provides an API for various search methods to access the query,
    and to add results to the result collection for future ranking.
    """

    def __init__(self, query: str, include_auto_definitions=None):
        self.query = Query(query)
        self.include_auto_definitions = first_non_none_value(
            self.query.auto, include_auto_definitions, default=False
        )
        self._results = {}
        self._verbose_messages = []

    include_auto_definition: bool
    _results: dict[WordformKey, types.Result]
    _verbose_messages: list[Any]

    def add_result(self, result: types.Result):
        if not isinstance(result, types.Result):
            raise TypeError(f"{result} is {type(result)}, not Result")
        key = result.wordform.key
        if key in self._results:
            self._results[key].add_features_from(result)
        else:
            self._results[key] = result

    def has_result(self, result: types.Result):
        return result.wordform.key in self._results

    def remove_result(self, result: types.Result):
        del self._results[result.wordform.key]

    def unsorted_results(self) -> Iterable[types.Result]:
        return self._results.values()

    def sorted_results(self) -> list[types.Result]:
        results = list(self._results.values())
        for r in results:
            r.assign_default_relevance_score()
        results.sort()
        return results

    def presentation_results(self) -> list[presentation.PresentationResult]:
        results = self.sorted_results()
        prefetch_related_objects(
            [r.wordform for r in results],
            "lemma__definitions__citations",
            "definitions__citations",
        )
        return [presentation.PresentationResult(r, search_run=self) for r in results]

    def serialized_presentation_results(self):
        results = self.presentation_results()
        wordforms = [r.wordform for r in results] + [r.wordform.lemma for r in results]

        Wordform.bulk_homograph_disambiguate(
            [wf for wf in wordforms if wf.is_lemma and wf.id is not None]
        )

        return [r.serialize() for r in results]

    def add_verbose_message(self, message):
        self._verbose_messages.append(message)

    @property
    def verbose_messages(self):
        return self._verbose_messages

    @property
    def internal_query(self):
        return self.query.query_string

    def __repr__(self):
        return f"SearchRun<query={self.query!r}>"
