import { app } from "../../../scripts/app.js";
import { ComfyWidgets } from "../../../scripts/widgets.js";

const GPT_IMAGE_NODE_NAMES = new Set([
    "ComfyUI-GPT-image Generate",
    "ComfyUI-GPT-image Edit",
]);

function getOrCreateCostWidget(node) {
    let widget = node.widgets?.find((item) => item.name === "gpt_image_cost");
    if (widget) {
        return widget;
    }

    widget = ComfyWidgets.STRING(
        node,
        "gpt_image_cost",
        ["STRING", { multiline: true }],
        app,
    ).widget;
    widget.inputEl.readOnly = true;
    widget.inputEl.style.border = "none";
    widget.inputEl.style.backgroundColor = "transparent";
    widget.serialize = false;
    return widget;
}

app.registerExtension({
    name: "ComfyUIGPTImageGenerationCost",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!GPT_IMAGE_NODE_NAMES.has(nodeData.name)) {
            return;
        }

        const originalOnExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            originalOnExecuted?.apply(this, arguments);

            const summary = message?.gpt_image_cost?.[0];
            if (!summary) {
                return;
            }

            const widget = getOrCreateCostWidget(this);
            widget.value = summary;
            const computedSize = this.computeSize();
            this.setSize([Math.max(this.size[0], 360), Math.max(this.size[1], computedSize[1])]);
            this.setDirtyCanvas(true, true);
        };
    },
});
