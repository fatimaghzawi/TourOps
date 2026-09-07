(function () {
    const root = document.querySelector("[data-cost-sheet]");
    if (!root) return;

    const capacityInput = document.querySelector("[data-cost-capacity]");
    const marginInput = document.querySelector("[data-cost-margin]");
    const priceInput = document.querySelector("[data-cost-price]");
    const override = document.querySelector("[data-override-services]");
    const apply = document.querySelector("[data-apply-suggested]");
    const inheritedMargin = document.querySelector("[data-inherited-margin]");

    function money(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return "—";
        if (Math.abs(number - Math.round(number)) < 0.001) {
            return "$" + Math.round(number).toLocaleString("en-US");
        }
        return "$" + number.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function commercial(amount) {
        if (amount <= 0) return 0;
        return Math.ceil(amount / 10) * 10;
    }

    function fromRow(row) {
        if (!row) return null;
        return {
            name: row.getAttribute("data-name") || "Service",
            supplier: row.getAttribute("data-supplier") || "",
            estimated_cost: Number(row.getAttribute("data-cost") || 0),
            cost_basis: row.getAttribute("data-basis") || "PER_GROUP",
        };
    }

    function selectedServices() {
        const useCatalog = !document.querySelector("[data-inherited-service]") || (override && override.checked);
        if (useCatalog) {
            return Array.from(document.querySelectorAll("[data-catalog-row] input[name='service_ids']:checked"))
                .map(function (input) { return fromRow(input.closest("[data-catalog-row]")); })
                .filter(Boolean);
        }
        return Array.from(document.querySelectorAll("[data-inherited-service]")).map(fromRow).filter(Boolean);
    }

    function sheet() {
        const services = selectedServices();
        const capacity = Math.max(parseInt(capacityInput && capacityInput.value, 10) || 0, 1);
        const margin = Number((marginInput && marginInput.value) || (inheritedMargin && inheritedMargin.value) || 30);
        let variable = 0;
        let group = 0;
        const lines = services.map(function (line) {
            const amount = Number(line.estimated_cost) || 0;
            const perPerson = line.cost_basis === "PER_PERSON" ? amount : amount / capacity;
            if (line.cost_basis === "PER_PERSON") variable += amount;
            else group += amount;
            return {
                name: line.name,
                supplier: line.supplier,
                estimated_cost: amount,
                basis_label: line.cost_basis === "PER_PERSON" ? "per traveler" : "for the departure",
                per_person_share: perPerson,
            };
        });
        const land = variable + group / capacity;
        const leftover = 1 - margin / 100;
        const suggested = leftover > 0 && land > 0 ? commercial(land / leftover) : 0;
        const typed = priceInput && priceInput.value !== "" ? Number(priceInput.value) : suggested;
        const selling = Number.isFinite(typed) ? typed : suggested;
        const profit = selling - land;
        const contribution = selling - variable;
        let breakEven = "—";
        if (group > 0 && contribution > 0) breakEven = Math.ceil(group / contribution) + " travelers";
        else if (group <= 0 && selling > variable) breakEven = "1 traveler";
        return {
            lines: lines,
            capacity: capacity,
            variable: variable,
            group: group,
            land: land,
            margin: margin,
            suggested: suggested,
            selling: selling,
            profit: profit,
            breakEven: breakEven,
            below: selling > 0 && selling < land,
        };
    }

    function setText(selector, text) {
        const node = root.querySelector(selector);
        if (node) node.textContent = text;
    }

    function render() {
        const data = sheet();
        const holder = root.querySelector("[data-cost-lines]");
        if (holder) {
            holder.replaceChildren();
            if (!data.lines.length) {
                const empty = document.createElement("p");
                empty.className = "muted";
                empty.textContent = "Tick supplier services to build land cost.";
                holder.appendChild(empty);
            } else {
                data.lines.forEach(function (line) {
                    const row = document.createElement("div");
                    row.className = "cost-line";
                    const left = document.createElement("div");
                    const title = document.createElement("strong");
                    title.textContent = line.name;
                    const meta = document.createElement("div");
                    meta.className = "muted";
                    meta.textContent = (line.supplier ? line.supplier + " · " : "") + money(line.estimated_cost) + " " + line.basis_label;
                    left.appendChild(title);
                    left.appendChild(meta);
                    const right = document.createElement("div");
                    right.textContent = money(line.per_person_share);
                    row.appendChild(left);
                    row.appendChild(right);
                    holder.appendChild(row);
                });
            }
        }
        const landRow = root.querySelector("[data-cost-land]");
        if (landRow && landRow.parentElement && landRow.parentElement.firstElementChild) {
            landRow.parentElement.firstElementChild.textContent = "Land cost / traveler at " + data.capacity + " pax";
        }
        const sug = root.querySelector("[data-cost-suggested]");
        if (sug && sug.parentElement && sug.parentElement.firstElementChild) {
            sug.parentElement.firstElementChild.textContent = "Suggested price (" + data.margin + "% margin)";
        }
        setText("[data-cost-variable]", money(data.variable));
        setText("[data-cost-group]", money(data.group));
        setText("[data-cost-land]", money(data.land));
        setText("[data-cost-suggested]", money(data.suggested));
        setText("[data-cost-selling]", money(data.selling));
        setText("[data-cost-profit]", money(data.profit));
        setText("[data-cost-breakeven]", data.breakEven);
        const warn = root.querySelector("[data-cost-warn]");
        if (warn) warn.hidden = !data.below;
        return data;
    }

    if (apply) {
        apply.addEventListener("click", function () {
            const data = render();
            if (priceInput && data.suggested > 0) {
                priceInput.value = data.suggested.toFixed(2);
                render();
            }
        });
    }

    document.addEventListener("input", function (event) {
        if (event.target === capacityInput || event.target === marginInput || event.target === priceInput) render();
    });
    document.addEventListener("change", function (event) {
        if (event.target && (event.target.name === "service_ids" || event.target === override)) render();
    });
    render();
})();
