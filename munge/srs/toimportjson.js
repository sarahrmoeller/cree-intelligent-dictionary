"use strict";

const { Transducer } = require("hfstol");
const { execIfMain } = require("execifmain");
const { readFile, writeFile } = require("fs/promises");
const { join: joinPath, resolve: resolvePath } = require("path");
const yargs = require("yargs");
const prettier = require("prettier");

const srcPath = resolvePath(__dirname, "..", "..", "src");

async function main() {
  const argv = yargs
    .strict()
    .demandCommand(0, 0)
    .option("output-file", { default: "srs-test-db.importjson" })
    .option("echo", {
      type: "boolean",
      default: false,
      description: "Print the generated JSON",
    })
    .option("dictionary-database", {
      type: "string",
      required: true,
    }).argv;

  const analyzer = new Transducer(
    joinPath(srcPath, "srseng/resources/fst/analyser-gt-desc.hfstol")
  );

  const lexicalDatabase = JSON.parse(
    (await readFile(argv.dictionaryDatabase)).toString()
  );

  let entries = [];

  for (const obj of lexicalDatabase) {
    const head = obj.text;

    const slug = head.replace(/[ \/]+/g, "_");

    const e = {
      head,
      slug,
      senses: [],
      linguistInfo: {
        wordClass: obj.word_class,
      },
    };
    for (const d of obj.defns) {
      e.senses.push({ definition: d, sources: ["OS"] });
    }

    // “--” (two hyphens) is defined as “paint it yellow”
    if (/^[.-]+$/.test(e.head)) {
      continue;
    }

    const analyses = analyzer.lookup_lemma_with_affixes(e.head);
    e.analyses = analyses;
    if (analyses.length !== 0) {
      e.analysis = analyses[0];
      if (e.analysis[2].includes("+V") && e.analysis[2].includes("+I")) {
        e.paradigm = "VI";
      }
    }

    if (argv.echo) {
      console.log(e);
    }
    entries.push(e);
  }

  const formattted = prettier.format(JSON.stringify(entries), {
    parser: "json",
  });

  await writeFile(argv.outputFile, formattted);
  console.log(`Wrote ${argv.outputFile}`);
}

execIfMain(main);
