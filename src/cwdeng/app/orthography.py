from functools import cache

from hfst_optimized_lookup import TransducerFile

from morphodict.analysis import FST_DIR


@cache
def cmro_lookup_fst():
    return TransducerFile(FST_DIR / "default-to-cmro.hfstol")


def to_cmro(s):
    results = cmro_lookup_fst().lookup(s)
    if not results:
        return s
    return results[0]
