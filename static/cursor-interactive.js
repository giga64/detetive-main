class InteractiveCursor {
  constructor() {
    this.el = document.createElement('div');
    this.el.style.cssText = 'position:fixed;left:0;top:0;width:16px;height:16px;border:1px solid rgba(6,182,212,.55);border-radius:50%;pointer-events:none;z-index:99999;transform:translate(-50%,-50%);transition:transform .1s ease-out;';
    document.body.appendChild(this.el);
    document.addEventListener('mousemove', (e) => {
      this.el.style.left = e.clientX + 'px';
      this.el.style.top = e.clientY + 'px';
    });
  }
}
window.InteractiveCursor = InteractiveCursor;
