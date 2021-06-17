"use strict";

const { Transducer } = require("hfstol");
const { execIfMain } = require("execifmain");
const { readFile, writeFile } = require("fs/promises");
const { join: joinPath, resolve: resolvePath } = require("path");
const yargs = require("yargs");
const prettier = require("prettier");
const expandTilde = require("expand-tilde");

const srcPath = resolvePath(__dirname, "..", "..", "src");

function makePrettier(data) {
  // Assume strings already contain JSON; otherwise, stringify
  if (typeof data !== "string") {
    data = JSON.stringify(data);
  }
  return prettier.format(data, {
    parser: "json",
  });
}

async function main() {
  const argv = yargs
    .strict()
    .demandCommand(0, 0)
    .option("output-file", { default: "arp-test-db.importjson" })
    .option("echo", {
      type: "boolean",
      default: false,
      description: "Print the generated JSON",
    })
    .option("dictionary-database", {
      type: "string",
      default: expandTilde("~/src/arp-db/arapaho_lexicon.json"),
    }).argv;

  const analyzer = new Transducer(
    joinPath(srcPath, "arpeng/resources/fst/arapahoverbs-analyzer.hfstol")
  );

  const lexicalDatabase = JSON.parse(
    (await readFile(argv.dictionaryDatabase)).toString()
  );

  let entries = [];

  for (const [key, obj] of Object.entries(lexicalDatabase)) {
    if (obj.status === "deleted") {
      continue;
    }

    const head = obj.base_form;

    const slug = head.replace(/[ \/]+/g, "_");

    const e = {
      head,
      slug,
      senses: [],
      linguistInfo: {
        pos: obj.pos,
      },
    };
    for (const sense of obj.senses) {
      const { definition } = sense;
      if (definition) {
        e.senses.push({ definition, sources: ["ALD"] });
      }
    }

    if (obj.pos === "vii") {
      e.paradigm = "II";
      const lemma = obj.lex.replace(/-/g, "");
      e.analysis = [[], lemma, []];
    } else {
      continue;
    }

    if (argv.echo) {
      console.log(makePrettier(e));
    }
    entries.push(e);
  }

  const formattted = makePrettier(entries);

  await writeFile(argv.outputFile, formattted);
  console.log(`Wrote ${argv.outputFile}`);
}

execIfMain(main);
