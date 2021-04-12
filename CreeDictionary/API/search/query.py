import unicodedata
from enum import Enum
from typing import Optional

import marshmallow.fields

from API.search import runner
from API.search.util import to_sro_circumflex


class Query:
    BOOL_KEYS = ["verbose", "auto"]

    def __init__(self, query_string):
        self.raw_query_string = query_string

        # Whitespace won't affect results, but the FST can't deal with it:
        query_string = query_string.strip()
        # All internal text should be in NFC form --
        # that is, all characters that can be composed are composed.
        query_string = unicodedata.normalize("NFC", query_string)

        query_string = query_string.lower()
        query_string = to_sro_circumflex(query_string)

        self.query_terms = []

        for token in query_string.split():
            # Whether this token has been used by some interpretation step
            consumed = False

            if ":" in token:
                user_key, value = token.split(":", 1)

                if user_key in Query.BOOL_KEYS:
                    consumed = True
                    setattr(self, user_key, value in marshmallow.fields.Boolean.truthy)
                elif user_key == "cvd":
                    consumed = True

                    try:
                        self.cvd = runner.CvdSearchType(int(value))
                    except ValueError:
                        for t in runner.CvdSearchType:
                            if value == t.name.lower():
                                self.cvd = t
                                break

            if not consumed:
                self.query_terms.append(token)

        self.query_string = " ".join(self.query_terms)

        self.is_valid = self.query_string != ""

    is_valid: bool
    verbose: Optional[bool] = None
    auto: Optional[bool] = None
