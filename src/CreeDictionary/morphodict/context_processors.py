from CreeDictionary.morphodict.orthography import ORTHOGRAPHY


def available_orthographies(request):
    return {
        "AVAILABLE_ORTHOGRAPHIES": {
            k: ORTHOGRAPHY.name_of(k) for k in ORTHOGRAPHY.available
        }
    }
