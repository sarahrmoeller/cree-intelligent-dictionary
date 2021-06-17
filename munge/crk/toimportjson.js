"use strict";

const { Transducer } = require("hfstol");
const { execIfMain } = require("execifmain");
const { readFile, writeFile } = require("fs/promises");
const { join: joinPath, resolve: resolvePath } = require("path");
const { inspect } = require("util");
const yargs = require("yargs");
const { intersection, min, isEqual, uniqBy } = require("lodash");
const prettier = require("prettier");

const srcPath = resolvePath(__dirname, "..", "..", "src");

const personalPronouns = new Set([
  // Personal pronouns
  "niya",
  "kiya",
  "wiya",
  "niyanân",
  "kiyânaw",
  "kiyawâw",
  "wiyawâw",
]);

const demonstrativePronouns = new Set([
  // Animate demonstratives
  "awa",
  "ana",
  "nâha",
  "ôki",
  "aniki",
  "nêki",
  // Inanimate demonstratives
  "ôma",
  "ôhi",
  "anima",
  "anihi",
  "nêma",
  "nêhi",
  // Inanimate/Obviative inanimate demonstratives
  "ôhi",
  "anihi",
  "nêhi",
]);

// If we’ve whittled choices down to just the analyses listed, take the first
// one in the list.
const tieBreakers = [
  ["maskwa+N+A+Sg", "maskwa+N+A+Obv"],
  ["niska+N+A+Sg", "niska+N+A+Obv"],
  ["môswa+N+A+Sg", "môswa+N+A+Obv"],
];

function getTieBreaker(analyses) {
  // FIXME: on all but tiny input dictionaries, tieBreakers should be turned
  // into a map by lemma.
  const smushed = analyses.map((a) => smushAnalysis(a));
  for (const tb of tieBreakers) {
    if (isEqual(tb, smushed)) {
      for (const a of analyses) {
        if (smushAnalysis(a) === tb[0]) {
          return a;
        }
      }
    }
  }
  return null;
}

async function readTestDbWords() {
  const fileContents = (
    await readFile(joinPath(srcPath, "CreeDictionary/res/test_db_words.txt"))
  ).toString();

  const ret = [];
  for (let line of fileContents.split("\n")) {
    line = line.trim();
    if (!line) {
      continue;
    }
    if (line.startsWith("#")) {
      // this is a comment line
      continue;
    }

    ret.push(line);
  }

  return ret;
}

let analyzer;

function FIXME_breakWordForFstWorkaround(a) {
  a = a.replace(/[yý]/g, "th");
  a = a.replace(/ê/g, "î");
  return a;
}

/**
 * If the FST analysis matches, return {analysis, paradigm}. Otherwise return null.
 */
function matchAnalysis(analysis, { head, pos }) {
  const [prefixTags, lemma, suffixTags] = analysis;
  if (
    lemma !== head &&
    // FIXME: hack to work around FST issues
    FIXME_breakWordForFstWorkaround(lemma) !==
      FIXME_breakWordForFstWorkaround(head)
  ) {
    // TODO: collect reasons
    return null;
  }

  if (pos.startsWith("I")) {
    if (suffixTags.includes("+Ipc")) {
      return { analysis, paradigm: null };
    }
  }

  if (
    pos === "PrA" &&
    personalPronouns.has(head) &&
    suffixTags.includes("+Pron") &&
    suffixTags.includes("+Pers")
  ) {
    return { analysis, paradigm: "personal-pronouns" };
  }

  if (
    (pos === "PrA" || pos === "PrI") &&
    demonstrativePronouns.has(head) &&
    suffixTags.includes("+Pron") &&
    suffixTags.includes("+Dem")
  ) {
    return { analysis, paradigm: "demonstrative-pronouns" };
  }

  if ((pos === "PrA" || pos === "PrI") && suffixTags.includes("+Pron")) {
    return { analysis, paradigm: null };
  }

  const specificWordClass = pos.split("-")[0];

  for (let [paradigmName, paradigmSpecificWordClass, paradigmTags] of [
    ["NA", "NA", ["+N", "+A"]],
    ["NI", "NI", ["+N", "+I"]],
    ["NDA", "NDA", ["+N", "+A", "+D"]],
    ["NDI", "NDI", ["+N", "+I", "+D"]],
    ["VTA", "VTA", ["+V", "+TA"]],
    ["VTI", "VTI", ["+V", "+TI"]],
    ["VAI", "VAI", ["+V", "+AI"]],
    ["VII", "VII", ["+V", "+II"]],
  ]) {
    if (
      specificWordClass === paradigmSpecificWordClass &&
      intersection(paradigmTags, suffixTags).length === paradigmTags.length
    ) {
      return { analysis, paradigm: paradigmName };
    }
  }
  return null;
}

function smushAnalysis(lemma_with_affixes) {
  const [prefixTags, lemma, suffixTags] = lemma_with_affixes;
  return [prefixTags.join(""), lemma, suffixTags.join("")].join("");
}

function inferAnalysis({ head, pos, key }) {
  let ok = false;

  // bug? cwd analyzer has duplicate results for nitha
  const analyses = uniqBy(
    analyzer.lookup_lemma_with_affixes(head),
    smushAnalysis
  );
  // Does FST analysis match POS from toolbox file?
  let matches = [];
  for (const a of analyses) {
    const match = matchAnalysis(a, { head, pos });
    if (match) {
      matches.push(match);
    }
  }
  let analysis, paradigm;
  if (matches.length > 0) {
    // ôma analyzes as +Pron+Def or +Pron+Dem; since we have a paradigm for
    // the latter, let’s prefer it.
    const matchesWithParadigms = matches.filter((m) => m.paradigm !== null);
    if (matchesWithParadigms.length > 0) {
      matches = matchesWithParadigms;
    }

    function analysisTagCount(analysis) {
      const [prefixTags, lemma, suffixTags] = analysis;
      return prefixTags.length + suffixTags.length;
    }

    const minTagCount = min(matches.map((m) => analysisTagCount(m.analysis)));
    const matchesWithMinTagCount = matches.filter(
      (m) => analysisTagCount(m.analysis) === minTagCount
    );
    if (matchesWithMinTagCount.length === 1) {
      const bestMatch = matchesWithMinTagCount[0];
      analysis = bestMatch.analysis;
      paradigm = bestMatch.paradigm;
      ok = true;
    } else if (getTieBreaker(matchesWithMinTagCount.map((m) => m.analysis))) {
      const tieBreakerAnalysis = getTieBreaker(
        matchesWithMinTagCount.map((m) => m.analysis)
      );
      for (const m of matchesWithMinTagCount) {
        if (m.analysis === tieBreakerAnalysis) {
          analysis = m.analysis;
          paradigm = m.paradigm;
          ok = true;
          break;
        }
      }
      if (!ok) {
        throw Error("tie breaker exists but was not applied");
      }
    } else {
      console.log(`${matches.length} matches for ${key}`);
      ok = false;
    }
  } else {
    console.log(`${matches.length} matches for ${key}`);
    ok = false;
  }

  return { analysis, paradigm, ok };
}

/**
 * A dictionary in importjson format.
 */
class ImportJsonDictionary {
  constructor() {
    this._entries = [];
    this._seenLemmas = new Set();
  }

  // TODO: return error information if unable to process input
  addFromNdjson(ndjsonObject, transliterator) {
    const head = transliterator(ndjsonObject.lemma?.sro);

    if (!head) {
      return;
    }

    const pos = ndjsonObject.dataSources?.CW?.pos;

    if (head.startsWith("-") || (head.endsWith("-") && pos !== "IPV")) {
      // TODO: handle morphemes
      return;
    }

    let analysis, paradigm;
    let ok = false;
    if (pos === "IPV") {
      analysis = null;
      paradigm = null;
      ok = true;
    } else if (head.includes(" ")) {
      analysis = null;
      paradigm = null;
      ok = true;
    } else {
      ({ analysis, paradigm, ok } = inferAnalysis({
        head,
        pos,
        key: ndjsonObject.key,
      }));
    }

    const linguistInfo = { pos };
    if (analysis) {
      linguistInfo.smushedAnalysis = smushAnalysis(analysis);
    }
    const stem = ndjsonObject.dataSources?.CW?.stm;
    if (stem) {
      linguistInfo.stem = stem;
    }

    this._entries.push({
      head,
      analysis,
      paradigm,
      senses: aggregateSenses(ndjsonObject),
      linguistInfo,
      slug: ndjsonObject.key,
      ok,
    });
    this._seenLemmas.add(head);
  }

  entries() {
    return this._entries.slice();
  }

  stats() {
    let ok = 0;
    let notOk = 0;
    for (const f of this._entries) {
      if (f.ok) {
        ok++;
      } else {
        notOk++;
      }
    }
    return { ok, notOk };
  }
}

function aggregateSenses(ndjsonObject) {
  const definitionToSources = new Map();
  for (const sourceAbbrevation in ndjsonObject.dataSources) {
    for (const s of ndjsonObject.dataSources[sourceAbbrevation].senses) {
      if (!definitionToSources.has(s.definition)) {
        definitionToSources.set(s.definition, []);
      }
      definitionToSources.get(s.definition).push(sourceAbbrevation);
    }
  }

  const ret = [];
  for (const [definition, sources] of definitionToSources.entries()) {
    ret.push({ definition, sources });
  }
  return ret;
}

function protoToWoods(s) {
  let ret = s;
  ret = ret.replace(/ý/g, "th");
  ret = ret.replace(/ê/g, "î");

  // BAD AND WRONG!! But lets us use the current buggy fst.
  ret = ret.replace(/y/g, "th");

  return ret;
}

function protoToPlains(s) {
  let ret = s;
  ret = ret.replace(/ý/g, "y");
  return ret;
}

async function main() {
  const argv = yargs
    .strict()
    .demandCommand(0, 0)
    .option("test-words-only", { type: "boolean", default: true })
    .option("woods", { type: "boolean", default: false })
    .option("output-file")
    .option("echo", {
      type: "boolean",
      default: false,
      description: "Print the generated JSON",
    })
    .option("dictionary-database", {
      type: "string",
      default: `${process.env.HOME}/alt/git/altlab/crk/dicts/database.ndjson`,
    }).argv;

  if (!argv.outputFile) {
    argv.outputFile = argv.woods
      ? "cwd-test-db.importjson"
      : "crk-test-db.importjson";
  }

  analyzer = new Transducer(
    joinPath(
      srcPath,
      argv.woods
        ? // FIXME: using relaxed analyzer until FST issues fixed
          "cwdeng/resources/fst/analyzer-gt-norm.hfstol"
        : "crkeng/resources/fst/crk-strict-analyzer-for-dictionary.hfstol"
    )
  );

  const transliterator = argv.woods ? protoToWoods : protoToPlains;

  const lexicalDatabase = (await readFile(argv.dictionaryDatabase)).toString();

  const testDbWords = await readTestDbWords();

  const importJsonDictionary = new ImportJsonDictionary();

  for (const piece of lexicalDatabase.split("\n")) {
    if (!piece.trim()) {
      continue;
    }

    const obj = JSON.parse(piece);

    const lemma = obj.lemma?.sro;
    if (argv.testWordsOnly && !testDbWords.includes(lemma)) {
      continue;
    }

    importJsonDictionary.addFromNdjson(
      obj,
      argv.woods ? protoToWoods : protoToPlains
    );
  }

  if (argv.testWordsOnly) {
    for (let w of testDbWords) {
      w = transliterator(w);
      if (!importJsonDictionary._seenLemmas.has(w)) {
        console.log(`Warning: test_db_words.txt entry ${w} not imported`);
      }
    }
  }

  const formattted = prettier.format(
    JSON.stringify(importJsonDictionary.entries()),
    { parser: "json" }
  );

  if (argv.echo) {
    console.log(formattted);
  }

  await writeFile(argv.outputFile, formattted);
  console.log(
    `Wrote ${argv.outputFile}: ${inspect(importJsonDictionary.stats())}`
  );
}

execIfMain(main);
