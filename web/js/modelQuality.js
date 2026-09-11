import { app } from "../../../scripts/app.js";

app.registerExtension({
    name: "ComfyUIGPTImageModelQuality",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!["ComfyUI-GPT-image Generate", "ComfyUI-GPT-image Edit"].includes(nodeData.name)) {
            return;
        }
        const qualities = nodeData.input.optional.quality[1].model_quality_options;
        const updateQuality = (node) => {
            const model = node.widgets?.find((widget) => widget.name === "model");
            const quality = node.widgets?.find((widget) => widget.name === "quality");
            const options = qualities[model?.value];
            if (!quality || !options) return;
            quality.options.values = [...options];
            if (!options.includes(quality.value)) {
                quality.value = "high";
                quality.callback?.(quality.value);
            }
            node.setDirtyCanvas(true, true);
        };

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);
            const node = this;
            const model = this.widgets?.find((widget) => widget.name === "model");
            if (model) {
                const callback = model.callback;
                model.callback = function () {
                    const result = callback?.apply(this, arguments);
                    updateQuality(node);
                    return result;
                };
            }
            updateQuality(this);
            return result;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = onConfigure?.apply(this, arguments);
            updateQuality(this);
            return result;
        };
    },
});
