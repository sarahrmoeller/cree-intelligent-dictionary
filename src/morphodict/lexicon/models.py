from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, Literal, Optional, Union
from urllib.parse import quote

from django.db import models, transaction
from django.db.models import Max, Q
from django.urls import reverse
from django.utils.functional import cached_property
from CreeDictionary.utils import (
    PartOfSpeech,
    WordClass,
    fst_analysis_parser,
    shared_res_dir,
)
from CreeDictionary.utils.cree_lev_dist import remove_cree_diacritics
from CreeDictionary.utils.types import FSTTag

from CreeDictionary.CreeDictionary.relabelling import LABELS

from CreeDictionary.API.schema import SerializedDefinition

# How long a wordform or dictionary head can be (number of Unicode scalar values)
# TODO: is this too small?
MAX_WORDFORM_LENGTH = 40

# Don't start evicting cache entries until we've seen over this many unique definitions:
MAX_SOURCE_ID_CACHE_ENTRIES = 4096

logger = logging.getLogger(__name__)


class WordformLemmaManager(models.Manager):
    """We are essentially always going to want the lemma

    So make preselecting it the default.
    """

    def get_queryset(self):
        return super().get_queryset().select_related("lemma")


# This type is the int pk for a saved wordform, or (text, analysis) for an unsaved one.
WordformKey = Union[int, tuple[str, str]]


class Wordform(models.Model):
    # Queries always do .select_related("lemma"):
    objects = WordformLemmaManager()

    text = models.CharField(max_length=MAX_WORDFORM_LENGTH)

    analysis = models.JSONField(null=True)

    paradigm = models.CharField(
        max_length=50,
        null=True,
        blank=False,
        default=None,
        help_text="If provided, this is the name of a static paradigm that this "
        "wordform belongs to. This name should match the filename in "
        "res/layouts/static/ WITHOUT the file extension.",
    )

    is_lemma = models.BooleanField(
        default=False,
        help_text="The wordform is chosen as lemma. This field defaults to true if according to fst the wordform is not"
        " analyzable or it's ambiguous",
    )

    lemma = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="inflections",
        help_text="The identified lemma of this wordform. Defaults to self",
        # This will never actually be null, but only the import creates wordforms, so this should be ok
        # self-referential blah blah blah
        null=True,
    )

    slug = models.CharField(max_length=50)

    # some lemmas have stems, they are shown in linguistic analysis
    # e.g. wâpam- is the stem for wâpamêw
    linguist_info_stem = models.CharField(
        max_length=128,
        blank=True,
    )

    linguist_info_pos = models.CharField(
        max_length=10,
        help_text="Inflectional category directly from source xml file",  # e.g. NI-3
    )

    class Meta:
        indexes = [
            # analysis is for faster user query (see search/lookup.py)
            models.Index(fields=["analysis"]),
            # text index benefits fast wordform matching (see search/lookup.py)
            models.Index(fields=["text"]),
            # When we *just* want to lookup text wordforms that are "lemmas"
            # (Note: Eddie thinks "head words" may also be lumped in as "lemmas")
            # Used by:
            #  - affix tree intialization
            #  - sitemap generation
            models.Index(fields=["is_lemma", "text"]),
            # pos and inflectional_category are used when generating the preverb cache:
            # models.Index(fields=["inflectional_category"]),
            # models.Index(fields=["pos"]),
        ]

    def __str__(self):
        return self.text

    def __repr__(self):
        cls_name = type(self).__name__
        return f"<{cls_name}: {self.text} {self.analysis}>"

    def get_absolute_url(self, ambiguity: Literal["allow", "avoid"] = "avoid") -> str:
        """
        :return: url that looks like
         "/words/nipaw" "/words/nipâw?pos=xx" "/words/nipâw?inflectional_category=xx" "/words/nipâw?analysis=xx" "/words/nipâw?id=xx"
         it's the least strict url that guarantees unique match in the database
        """
        assert self.is_lemma, "There is no page for non-lemmas"
        lemma_url = reverse(
            "cree-dictionary-index-with-lemma", kwargs={"lemma_text": self.text}
        )

        if ambiguity == "allow":
            # avoids doing an expensive lookup to disambiguate
            return lemma_url

        if self.homograph_disambiguator is not None:
            lemma_url += f"?{self.homograph_disambiguator}={quote(str(getattr(self, self.homograph_disambiguator)))}"

        return lemma_url


class DictionarySource(models.Model):
    """
    Represents bibliographic information for a set of definitions.

    A Definition is said to cite a DictionarySource.
    """

    # A short, unique, uppercased ID. This will be exposed to users!
    #  e.g., CW for "Cree: Words"
    #     or MD for "Maskwacîs Dictionary"
    abbrv = models.CharField(max_length=8, primary_key=True)

    # Bibliographic information:
    title = models.CharField(
        max_length=256,
        null=False,
        blank=False,
        help_text="What is the primary title of the dictionary source?",
    )
    author = models.CharField(
        max_length=512,
        blank=True,
        help_text="Separate multiple authors with commas. See also: editor",
    )
    editor = models.CharField(
        max_length=512,
        blank=True,
        help_text=(
            "Who edited or compiled this volume? "
            "Separate multiple editors with commas."
        ),
    )
    year = models.IntegerField(
        null=True, blank=True, help_text="What year was this dictionary published?"
    )
    publisher = models.CharField(
        max_length=128, blank=True, help_text="What was the publisher?"
    )
    city = models.CharField(
        max_length=64, blank=True, help_text="What is the city of the publisher?"
    )

    def __str__(self):
        """
        Will print a short citation like:

            [CW] “Cree : Words” (Ed. Arok Wolvengrey)
        """
        # These should ALWAYS be present
        abbrv = self.abbrv
        title = self.title

        # Both of these are optional:
        author = self.author
        editor = self.editor

        author_or_editor = ""
        if author:
            author_or_editor += f" by {author}"
        if editor:
            author_or_editor += f" (Ed. {editor})"

        return f"[{abbrv}]: “{title}”{author_or_editor}"


class Definition(models.Model):
    text = models.CharField(max_length=200)

    # A definition **cites** one or more dictionary sources.
    citations = models.ManyToManyField(DictionarySource)

    # A definition defines a particular wordform
    wordform = models.ForeignKey(
        Wordform, on_delete=models.CASCADE, related_name="definitions"
    )

    # If this definition is auto-generated based on a different definition,
    # point at the source definition.
    auto_translation_source = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True
    )

    # Why this property exists:
    # because DictionarySource should be its own model, but most code only
    # cares about the source IDs. So this removes the coupling to how sources
    # are stored and returns the source IDs right away.
    @property
    def source_ids(self) -> list[str]:
        """
        A tuple of the source IDs that this definition cites.
        """
        return sorted(set(c.abbrv for c in self.citations.all()))

    def serialize(self) -> SerializedDefinition:
        """
        :return: json parsable format
        """
        return {"text": self.text, "source_ids": self.source_ids}

    def __str__(self):
        return self.text


class TargetLanguageKeyword(models.Model):
    # override pk to allow use of bulk_create
    id = models.PositiveIntegerField(primary_key=True)

    text = models.CharField(max_length=20)

    # N.B., this says "lemma", but it can actually be ANY Wordform
    # (lemma or non-lemma)
    lemma = models.ForeignKey(
        Wordform, on_delete=models.CASCADE, related_name="english_keyword"
    )

    def __repr__(self) -> str:
        return f"<EnglishKeyword(text={self.text!r} of {self.lemma!r} ({self.id})>"

    class Meta:
        indexes = [models.Index(fields=["text"])]


class _WordformCache:
    @cached_property
    def MORPHEME_RANKINGS(self) -> Dict[str, float]:
        logger.debug("reading morpheme rankings")
        ret = {}

        lines = (
            Path(shared_res_dir / "W_aggr_corp_morph_log_freq.txt")
            .read_text()
            .splitlines()
        )
        for line in lines:
            cells = line.split("\t")
            # todo: use the third row
            if len(cells) >= 2:
                freq, morpheme, *_ = cells
                ret[morpheme] = float(freq)
        return ret

    def preload(self):
        # Accessing these cached properties will preload them
        self.MORPHEME_RANKINGS


wordform_cache = _WordformCache()
