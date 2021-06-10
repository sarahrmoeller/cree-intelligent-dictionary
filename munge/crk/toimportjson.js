"use strict";

const { Transducer } = require("hfstol");
const { execIfMain } = require("execifmain");
const { readFile, writeFile } = require("fs/promises");
const { join: joinPath, resolve: resolvePath } = require("path");
const { inspect } = require("util");
const yargs = require("yargs");
const { intersection } = require("lodash");

const srcPath = resolvePath(__dirname, "..", "..", "src");

const ndJsonPosToParadigm = new Map([["NA-1", "NA"]]);

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

const crkAnalyzer = new Transducer(
  joinPath(
    srcPath,
    "crkeng/resources/fst/crk-strict-analyzer-for-dictionary.hfstol"
  )
);

/**
 * If the FST analysis matches, return {analysis, paradigm}. Otherwise return null.
 */
function matchAnalysis(analysis, { head, pos }) {
  const [prefixTags, lemma, suffixTags] = analysis;
  if (lemma !== head) {
    // TODO: collect reasons
    return null;
  }

  if (pos.startsWith("I")) {
    return { analysis: null, paradigm: null };
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

  const swc = pos.split("-")[0];

  for (let [paradigmName, paradigmSwc, paradigmTags] of [
    ["noun-na", "NA", ["+N", "+A"]],
    ["noun-ni", "NI", ["+N", "+I"]],
    ["noun-nad", "NDA", ["+N", "+A", "+D"]],
    ["noun-nid", "NDI", ["+N", "+I", "+D"]],
    ["verb-ta", "VTA", ["+V", "+TA"]],
    ["verb-ti", "VTI", ["+V", "+TI"]],
    ["verb-ai", "VAI", ["+V", "+AI"]],
    ["verb-ii", "VII", ["+V", "+II"]],
  ]) {
    if (
      swc === paradigmSwc &&
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

/**
 * A dictionary in importjson format.
 */
class ImportJsonDictionary {
  constructor() {
    this._entries = [];
  }

  // TODO: return error information if unable to process input
  addFromNdjson(ndjsonObject) {
    const head = ndjsonObject.lemma?.plains;

    if (!head) {
      return;
    }

    if (head.includes(" ")) {
      // TODO: handle phrases
      return;
    }
    if (head.startsWith("-") || head.endsWith("-")) {
      // TODO: handle morphemes
      return;
    }

    let ok = true;

    const pos = ndjsonObject.dataSources?.CW?.pos;

    const analyses = crkAnalyzer.lookup_lemma_with_affixes(head);
    // Does FST analysis match POS from toolbox file?
    const matches = [];
    for (const a of analyses) {
      const match = matchAnalysis(a, { head, pos });
      if (match) {
        matches.push(match);
      }
    }
    let analysis, paradigm;
    if (matches.length === 1) {
      const match = matches[0];
      analysis = match.analysis;
      paradigm = match.paradigm;
    } else {
      ok = false;
    }

    const linguistInfo = { pos };
    if (analysis) {
      linguistInfo.smushedAnalysis = smushAnalysis(analysis);
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

async function main() {
  const argv = yargs
    .strict()
    .demandCommand(0, 0)
    .option("test-words-only", { type: "boolean", default: true })
    .option("output-file", { default: "crk-test-db.importjson" })
    .option("echo", {
      type: "boolean",
      default: false,
      description: "Print the generated JSON",
    })
    .option("dictionary-database", {
      type: "string",
      default: `${process.env.HOME}/alt/git/altlab/crk/dicts/database.ndjson`,
    }).argv;

  const lexicalDatabase = (await readFile(argv.dictionaryDatabase)).toString();

  const testDbWords = await readTestDbWords();

  const importJsonDictionary = new ImportJsonDictionary();

  for (const piece of lexicalDatabase.split("\n")) {
    if (!piece.trim()) {
      continue;
    }

    const obj = JSON.parse(piece);

    const lemma = obj.lemma?.plains;
    if (argv.testWordsOnly && !testDbWords.includes(lemma)) {
      continue;
    }

    importJsonDictionary.addFromNdjson(obj);
  }

  const formattted = JSON.stringify(importJsonDictionary.entries(), null, 2);

  if (argv.echo) {
    console.log(formattted);
  }

  await writeFile(argv.outputFile, formattted);
  console.log(
    `Wrote ${argv.outputFile}: ${inspect(importJsonDictionary.stats())}`
  );
}

execIfMain(main);
