window.OneSeekNarrative = {
  stages: [
    'Coletando dados...',
    'Cruzando vínculos...',
    'Validando consistência...',
    'Concluindo relatório...'
  ],
  start(targetEl) {
    if (!targetEl) return { stop() {} };
    let idx = 0;
    targetEl.textContent = this.stages[idx];
    const timer = setInterval(() => {
      idx = (idx + 1) % this.stages.length;
      targetEl.textContent = this.stages[idx];
    }, 1300);
    return { stop() { clearInterval(timer); } };
  }
};
