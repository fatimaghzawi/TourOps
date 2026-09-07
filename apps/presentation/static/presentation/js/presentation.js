(function () {
    const root = document.querySelector("[data-theater]");
    if (!root) return;
    var moving = false;

    const booked = Math.max(0, parseInt(root.getAttribute("data-booked") || "22", 10) || 0);
    const capacity = Math.max(1, parseInt(root.getAttribute("data-capacity") || "30", 10) || 30);
    const avail = root.getAttribute("data-avail");
    document.querySelectorAll("[data-avail]").forEach(function (node) {
        if (avail) node.textContent = avail;
    });
    document.querySelectorAll("[data-seats]").forEach(function (strip) {
        strip.innerHTML = "";
        for (var i = 0; i < capacity; i += 1) {
            var cell = document.createElement("span");
            cell.className = "seat" + (i < booked ? " is-in" : "");
            strip.appendChild(cell);
        }
    });

    function go(href) {
        if (!href || moving) return;
        moving = true;
        window.location.href = href;
    }

    document.addEventListener("keydown", function (event) {
        if (event.repeat) return;
        if (event.target && /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) return;
        if (event.key === "Escape") {
            go(root.getAttribute("data-exit") || "/presentation/");
            return;
        }
        if (event.key === "ArrowRight") go(root.getAttribute("data-next"));
        if (event.key === "ArrowLeft") go(root.getAttribute("data-prev"));
    });

    function refresh() {
        fetch("/presentation/state/", { credentials: "same-origin" })
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                if (!data || !data.capacity) return;
                var text = data.booked + "/" + data.capacity + " seats";
                if (data.planned) text += " · " + data.confirmed + "/" + data.planned + " confirmed";
                document.querySelectorAll("[data-theater-live]").forEach(function (node) {
                    node.textContent = text;
                });
            })
            .catch(function () {});
    }
    refresh();
    setInterval(refresh, 8000);
})();
