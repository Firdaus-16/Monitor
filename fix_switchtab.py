#!/usr/bin/env python3
import io

with io.open('templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# HANYA ganti fungsi switchTab
old = 'function switchTab(tabId) {\n            // Hide all tab areas\n            document.querySelectorAll(\'.tab-content-area\').forEach(el => el.classList.add(\'d-none\'));\n            // Remove active from all nav buttons\n            document.querySelectorAll(\'.nav-link-tab\').forEach(el => el.classList.remove(\'active\'));\n\n            // Show selected tab\n            const target = document.getElementById(tabId);\n            if (target) target.classList.remove(\'d-none\');\n\n            // Set active class on navbar button\n            const btn = document.getElementById(\'btn-\' + tabId);\n            if (btn) btn.classList.add(\'active\');\n\n            // Trigger tab-specific initializations\n            if (tabId === \'tab-map\') {\n                setTimeout(initOrInvalidateMap, 100);\n            } else if (tabId === \'tab-stats\') {\n                setTimeout(loadCharts, 100);\n            }\n        }'

new = 'function switchTab(tabId) {\n            try {\n                // Hide all tab areas\n                document.querySelectorAll(\'.tab-content-area\').forEach(el => el.classList.add(\'d-none\'));\n                // Remove active from all nav buttons\n                document.querySelectorAll(\'.nav-link-tab\').forEach(el => el.classList.remove(\'active\'));\n\n                // Show selected tab\n                const target = document.getElementById(tabId);\n                if (target) target.classList.remove(\'d-none\');\n\n                // Set active class on navbar button\n                const btn = document.getElementById(\'btn-\' + tabId);\n                if (btn) btn.classList.add(\'active\');\n\n                // Trigger tab-specific initializations\n                if (tabId === \'tab-map\') {\n                    setTimeout(() => { if (typeof initOrInvalidateMap === \'function\') initOrInvalidateMap(); }, 100);\n                } else if (tabId === \'tab-stats\') {\n                    setTimeout(() => { if (typeof loadCharts === \'function\') loadCharts(); }, 100);\n                } else if (tabId === \'tab-devices\') {\n                    if (typeof loadDevices === \'function\') loadDevices();\n                }\n            } catch (e) {\n                console.error(\'Error switching tab:\', e);\n            }\n        }'

if old in content:
    content = content.replace(old, new, 1)
    print("Replaced switchTab")
else:
    print("switchTab pattern NOT found")

with io.open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("Done switchTab")