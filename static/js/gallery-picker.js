(function () {
    document.querySelectorAll("[data-gallery-picker]").forEach(function (root) {
        const input = root.querySelector('input[type="file"][name="gallery"]');
        const list = root.querySelector("[data-gallery-pending]");
        if (!input || !window.DataTransfer) return;
        const max = parseInt(root.getAttribute("data-gallery-max") || "8", 10) || 8;
        let files = [];

        function apply() {
            const transfer = new DataTransfer();
            files.forEach(function (file) {
                transfer.items.add(file);
            });
            input.files = transfer.files;
            if (!list) return;
            list.replaceChildren();
            if (!files.length) {
                list.hidden = true;
                return;
            }
            list.hidden = false;
            files.forEach(function (file, index) {
                const item = document.createElement("li");
                const name = document.createElement("span");
                name.textContent = file.name;
                const remove = document.createElement("button");
                remove.type = "button";
                remove.className = "tiny";
                remove.textContent = "Remove";
                remove.addEventListener("click", function () {
                    files = files.filter(function (_kept, i) {
                        return i !== index;
                    });
                    apply();
                });
                item.appendChild(name);
                item.appendChild(remove);
                list.appendChild(item);
            });
        }

        input.addEventListener("change", function () {
            Array.from(input.files || []).forEach(function (file) {
                const duplicate = files.some(function (kept) {
                    return kept.name === file.name && kept.size === file.size && kept.lastModified === file.lastModified;
                });
                if (!duplicate && files.length < max) files.push(file);
            });
            apply();
        });
    });
})();
