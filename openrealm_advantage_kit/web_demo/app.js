const steps = [
  "Parse prompt into safe intent",
  "Create bounded OpenRealm recipe",
  "Validate identifiers, budgets, and unsafe tokens",
  "Generate preview and approval checklist",
  "Emit Luanti mod from deterministic templates",
  "Store audit and rollback metadata"
];

const safety = [
  "AI never mutates the world directly",
  "All changes are previewed before build",
  "Structure writes are budgeted",
  "Protected areas are checked in-world",
  "Rollback is stored before placement"
];

function render() {
  document.getElementById('steps').innerHTML = steps.map(s => `<li>${s}</li>`).join('');
  document.getElementById('safety').innerHTML = safety.map(s => `<li>${s}</li>`).join('');
  const prompt = document.getElementById('prompt').value;
  document.getElementById('preview').innerHTML = `
    <div class="preview-world">${prompt.includes('moonstone') ? 'Moonstone Ore Pack' : 'Cozy Lakeside Village'}</div>
    <p><span class="badge">Preview required</span><span class="badge">Approval required</span><span class="badge">Rollback ready</span></p>
  `;
}

document.getElementById('generate').addEventListener('click', render);
render();
