(function () {
  document.addEventListener('click', function (event) {
    const button = event.target.closest('button, .btn, .action-btn, .btn-back, .btn-export');
    if (!button) return;
    button.animate([
      { transform: 'scale(1)' },
      { transform: 'scale(0.97)' },
      { transform: 'scale(1)' }
    ], { duration: 180, easing: 'ease-out' });
  });
})();
