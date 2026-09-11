import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { execFileSync } from "node:child_process";

const definitions = JSON.parse(execFileSync(process.env.PYTHON || "python", ["-c",
    "import sys,json; sys.path.insert(0,'tests'); from _loader import import_module; n=import_module('py.nodes'); print(json.dumps({k: v.INPUT_TYPES() for k,v in [('Generate',n.GPTImageGenerateNode),('Edit',n.GPTImageEditNode)]}))",
], { encoding: "utf8" }));
let extension;
vm.runInNewContext(
    readFileSync(new URL("../web/js/modelQuality.js", import.meta.url), "utf8").replace(/^import .*;\r?\n/, ""),
    { app: { registerExtension(value) { extension = value; } } },
);

for (const name of ["Generate", "Edit"]) {
    let callbacks = 0;
    class Node {
        constructor() {
            this.widgets = [
                { name: "model", value: "gpt-image-2", callback() { callbacks++; } },
                { name: "quality", value: "auto", options: {} },
            ];
        }
        setDirtyCanvas() {}
    }
    await extension.beforeRegisterNodeDef(Node, { name: `ComfyUI-GPT-image ${name}`, input: definitions[name] });
    const node = new Node();
    node.onNodeCreated();
    const [model, quality] = node.widgets;
    assert.equal(quality.options.values.includes("max"), false);
    for (const value of ["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"]) {
        model.value = value;
        model.callback();
        assert.equal(quality.options.values.includes("xhigh"), true);
        quality.value = "max";
        node.onConfigure();
        assert.equal(quality.value, "max");
        model.value = "gpt-image-2";
        model.callback();
        assert.equal(quality.value, "high");
        assert.equal(quality.options.values.includes("max"), false);
    }
    model.value = "gpt-image-1.5";
    quality.value = "medium";
    node.onConfigure();
    assert.equal(quality.value, "medium");
    assert.equal(callbacks, 4);
}
console.log("Model quality: Generate/Edit switching, workflow restore, and original callbacks passed.");
