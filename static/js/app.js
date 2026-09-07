(function () {
    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    }
    window.touropsFetch = function (url, options) {
        const opts = options || {};
        const headers = Object.assign({}, opts.headers || {});
        const method = (opts.method || "GET").toUpperCase();
        if (method !== "GET" && method !== "HEAD") {
            headers["X-CSRFToken"] = csrfToken();
        }
        return fetch(url, Object.assign({}, opts, { headers, credentials: "same-origin" }));
    };

    const sidebar = document.getElementById("sidebar");
    const toggle = document.querySelector("[data-sidebar-toggle]");
    if (toggle && sidebar) {
        toggle.addEventListener("click", function () {
            sidebar.classList.toggle("open");
        });
    }

    const collapse = document.querySelector("[data-sidebar-collapse]");
    if (collapse) {
        if (localStorage.getItem("tourops-sidebar") === "collapsed") {
            document.body.classList.add("sidebar-collapsed");
        }
        collapse.addEventListener("click", function () {
            document.body.classList.toggle("sidebar-collapsed");
            localStorage.setItem(
                "tourops-sidebar",
                document.body.classList.contains("sidebar-collapsed") ? "collapsed" : "open"
            );
        });
    }

    const quickBtn = document.querySelector("[data-quick-create]");
    const quickMenu = document.querySelector("[data-quick-menu]");
    if (quickBtn && quickMenu) {
        quickBtn.addEventListener("click", function (event) {
            event.stopPropagation();
            quickMenu.classList.toggle("open");
        });
        document.addEventListener("click", function () {
            quickMenu.classList.remove("open");
        });
    }

    const drops = Array.prototype.slice.call(document.querySelectorAll("details.nav-drop"));
    function closeDrops(except) {
        drops.forEach(function (drop) {
            if (drop !== except) drop.removeAttribute("open");
        });
    }
    drops.forEach(function (drop) {
        drop.addEventListener("toggle", function () {
            if (drop.open) closeDrops(drop);
        });
    });
    document.addEventListener("click", function (event) {
        if (!event.target.closest("details.nav-drop")) closeDrops();
    });
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeDrops();
    });

    document.querySelectorAll("[data-chips]").forEach(function (group) {
        group.addEventListener("click", function (event) {
            const chip = event.target.closest(".chip");
            if (!chip) return;
            group.querySelectorAll(".chip").forEach(function (item) {
                item.classList.remove("is-on");
            });
            chip.classList.add("is-on");
        });
    });

    function money(n) {
        return "$" + Math.round(n).toLocaleString("en-US");
    }

    const amountInput = document.querySelector("[data-pay-amount]");
    if (amountInput) {
        const remainingEl = document.querySelector("[data-pay-remaining]");
        const afterEl = document.querySelector("[data-pay-after]");
        const errEl = document.querySelector("[data-pay-error]");
        const cap = Number(amountInput.getAttribute("data-max") || 0);
        function updatePay() {
            const value = Number(amountInput.value || 0);
            const after = cap - value;
            if (afterEl) afterEl.textContent = money(Math.max(after, 0));
            if (remainingEl) remainingEl.textContent = money(cap);
            if (errEl) {
                const over = value > cap + 0.001;
                errEl.classList.toggle("show", over);
                if (afterEl) afterEl.classList.toggle("warn", over || after < 0);
            }
        }
        amountInput.addEventListener("input", updatePay);
        updatePay();
    }

    const spAmount = document.querySelector("[data-sp-amount]");
    if (spAmount) {
        const cap = Number(spAmount.getAttribute("data-max") || 0);
        const afterEl = document.querySelector("[data-sp-after]");
        const errEl = document.querySelector("[data-sp-error]");
        spAmount.addEventListener("input", function () {
            const value = Number(spAmount.value || 0);
            if (value > cap) {
                spAmount.value = String(cap);
            }
            const used = Number(spAmount.value || 0);
            if (afterEl) afterEl.textContent = money(cap - used);
            if (errEl) errEl.classList.toggle("show", value > cap);
        });
    }

    document.querySelectorAll("[data-open-drawer]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            const id = btn.getAttribute("data-open-drawer");
            const drawer = document.getElementById(id);
            const back = document.getElementById(id + "-back");
            if (drawer) drawer.classList.add("open");
            if (back) back.classList.add("open");
        });
    });
    document.querySelectorAll("[data-close-drawer]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            document.querySelectorAll(".drawer, .drawer-back").forEach(function (el) {
                el.classList.remove("open");
            });
        });
    });

    const wizard = document.querySelector("[data-wizard]");
    if (wizard) {
        let step = 1;
        const total = 6;
        const price = 650;
        function show() {
            wizard.querySelectorAll("[data-step]").forEach(function (panel) {
                panel.hidden = Number(panel.getAttribute("data-step")) !== step;
            });
            wizard.querySelectorAll("[data-wz]").forEach(function (item) {
                const n = Number(item.getAttribute("data-wz"));
                item.classList.toggle("is-on", n === step);
            });
        }
        function recalc() {
            const travelers = Number(wizard.querySelector("[data-travelers]")?.value || 4);
            const discount = Number(wizard.querySelector("[data-discount]")?.value || 0);
            const taxRate = 0.11;
            const subtotal = travelers * price;
            const afterDisc = Math.max(subtotal - discount, 0);
            const tax = Math.round(afterDisc * taxRate);
            const totalAmt = afterDisc + tax;
            const set = function (name, val) {
                wizard.querySelectorAll("[data-sum='" + name + "']").forEach(function (el) {
                    el.textContent = money(val);
                });
            };
            set("sub", subtotal);
            set("disc", discount);
            set("tax", tax);
            set("total", totalAmt);
            wizard.querySelectorAll("[data-sum='pax']").forEach(function (el) {
                el.textContent = String(travelers);
            });
        }
        wizard.addEventListener("click", function (event) {
            const next = event.target.closest("[data-next]");
            const prev = event.target.closest("[data-prev]");
            const pick = event.target.closest(".pick");
            if (pick) {
                pick.parentElement.querySelectorAll(".pick").forEach(function (p) {
                    p.classList.remove("is-on");
                });
                pick.classList.add("is-on");
            }
            if (next) {
                step = Math.min(total, step + 1);
                show();
            }
            if (prev) {
                step = Math.max(1, step - 1);
                show();
            }
        });
        wizard.addEventListener("input", recalc);
        show();
        recalc();
    }

    const capBar = document.querySelector("[data-animate-cap]");
    if (capBar) {
        const fill = capBar.querySelector("i");
        const label = document.querySelector("[data-cap-label]");
        requestAnimationFrame(function () {
            fill.style.width = capBar.getAttribute("data-to") + "%";
        });
        if (label && capBar.getAttribute("data-demo") === "1") {
            setTimeout(function () {
                label.textContent = "20 / 25 seats";
                fill.style.width = "80%";
            }, 900);
        }
    }

    const toast = document.getElementById("app-toast");
    document.querySelectorAll("[data-toast]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            if (!toast) return;
            toast.textContent = btn.getAttribute("data-toast");
            toast.classList.add("show");
            setTimeout(function () {
                toast.classList.remove("show");
            }, 3200);
        });
    });

    document.querySelectorAll("[data-settings-tab]").forEach(function (tab) {
        tab.addEventListener("click", function (event) {
            event.preventDefault();
            const name = tab.getAttribute("data-settings-tab");
            document.querySelectorAll("[data-settings-tab]").forEach(function (t) {
                t.classList.toggle("is-on", t === tab);
            });
            document.querySelectorAll("[data-settings-panel]").forEach(function (panel) {
                panel.hidden = panel.getAttribute("data-settings-panel") !== name;
            });
        });
    });

    document.querySelectorAll("[data-copy-email]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            const source = document.querySelector("[data-email-copy]");
            const text = source ? source.textContent : "";
            if (!text) return;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text);
            }
            const toast = document.getElementById("app-toast");
            if (toast) {
                toast.textContent = "Email copied. The supplier does not use TourOps.";
                toast.classList.add("show");
                setTimeout(function () {
                    toast.classList.remove("show");
                }, 2800);
            }
        });
    });

    document.querySelectorAll("[data-live-filters]").forEach(function (live) {
        const q = live.querySelector("[data-live-q]");
        const fields = Array.prototype.slice.call(live.querySelectorAll("[data-live-field], [data-live-status]"));
        const host = live.closest("main") || document;
        const rows = Array.prototype.slice.call(host.querySelectorAll("[data-live-row]"));
        const empty = host.querySelector("[data-live-empty]");
        function applyLiveFilter() {
            const needle = ((q && q.value) || "").trim().toLowerCase();
            const checks = fields.map(function (field) {
                return {
                    key: field.getAttribute("data-live-field") || "status",
                    value: (field.value || "").trim().toUpperCase(),
                };
            });
            let visible = 0;
            rows.forEach(function (row) {
                const hay = (row.getAttribute("data-search") || "").toLowerCase();
                let show = !needle || hay.indexOf(needle) !== -1;
                checks.forEach(function (check) {
                    if (!check.value || !show) return;
                    const rowVal = (row.getAttribute("data-" + check.key) || "").toUpperCase();
                    if (rowVal !== check.value) show = false;
                });
                row.hidden = !show;
                if (show) visible += 1;
            });
            if (empty) empty.hidden = !rows.length || visible !== 0;
        }
        if (q) q.addEventListener("input", applyLiveFilter);
        fields.forEach(function (field) {
            field.addEventListener("change", applyLiveFilter);
            field.addEventListener("input", applyLiveFilter);
        });
        applyLiveFilter();
    });

    document.querySelectorAll("form[data-autosubmit]").forEach(function (form) {
        form.querySelectorAll("select, input[type='date'], input[type='month']").forEach(function (el) {
            el.addEventListener("change", function () {
                form.requestSubmit();
            });
        });
        form.querySelectorAll("input[type='search'], input[name='q'], input[name='entity_id']").forEach(function (el) {
            let timer;
            el.addEventListener("input", function () {
                clearTimeout(timer);
                timer = setTimeout(function () {
                    form.requestSubmit();
                }, 280);
            });
        });
    });

    (function confirmDialog() {
        const layer = function () { return document.getElementById("app-confirm"); };
        let pending = null;
        function flavor(message, form) {
            const text = (message || "").toLowerCase();
            const title = (form && form.getAttribute("data-confirm-title")) || "";
            const ok = (form && form.getAttribute("data-confirm-ok")) || "";
            if (title && ok) return { title: title, ok: ok };
            if (text.indexOf("void") !== -1) return { title: "Take this off the ledger?", ok: "Void it" };
            if (text.indexOf("delete") !== -1) return { title: "This can’t be undone", ok: "Delete it" };
            if (text.indexOf("cancel") !== -1) return { title: "Walk this back?", ok: "Cancel it" };
            if (text.indexOf("remove") !== -1) return { title: "Clear this file?", ok: "Remove it" };
            return { title: title || "Just checking", ok: ok || "Yes, continue" };
        }
        function closeConfirm() {
            const host = layer();
            if (host) host.hidden = true;
            pending = null;
        }
        function openConfirm(form) {
            const host = layer();
            if (!host) {
                if (window.confirm(form.getAttribute("data-confirm") || "Continue?")) {
                    HTMLFormElement.prototype.submit.call(form);
                }
                return;
            }
            pending = form;
            const copy = flavor(form.getAttribute("data-confirm") || "", form);
            const title = host.querySelector("#confirm-title");
            const body = host.querySelector("#confirm-body");
            const ok = host.querySelector("#confirm-ok");
            if (title) title.textContent = copy.title;
            if (body) body.textContent = form.getAttribute("data-confirm") || "";
            if (ok) ok.textContent = copy.ok;
            host.hidden = false;
            if (ok) ok.focus();
        }
        document.addEventListener("submit", function (event) {
            const form = event.target.closest("form[data-confirm]");
            if (!form || form.getAttribute("data-confirm-ready") === "1") return;
            const message = form.getAttribute("data-confirm");
            if (!message) return;
            event.preventDefault();
            openConfirm(form);
        }, true);
        document.addEventListener("click", function (event) {
            if (event.target.closest("[data-confirm-dismiss]")) {
                closeConfirm();
                return;
            }
            if (event.target.closest("#confirm-ok") && pending) {
                const form = pending;
                closeConfirm();
                form.setAttribute("data-confirm-ready", "1");
                HTMLFormElement.prototype.submit.call(form);
            }
        });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") closeConfirm();
        });
    })();

    (function lightbox() {
        const host = document.getElementById("app-lightbox");
        if (!host) return;
        const frame = host.querySelector("img");
        function closeBox() { host.hidden = true; }
        document.addEventListener("click", function (event) {
            const shot = event.target.closest("[data-gallery-src]");
            if (shot) {
                event.preventDefault();
                if (frame) {
                    frame.src = shot.getAttribute("data-gallery-src");
                    frame.alt = shot.getAttribute("data-gallery-alt") || "";
                }
                host.hidden = false;
                return;
            }
            if (event.target.closest("[data-lightbox-close]")) closeBox();
        });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") closeBox();
        });
    })();
})();
