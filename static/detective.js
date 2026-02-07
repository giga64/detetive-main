// Alternância de tema claro/escuro
function setTheme(theme) {
  if (theme === 'dark') {
    document.body.classList.add('dark');
    localStorage.setItem('theme', 'dark');
    document.getElementById('theme-icon').textContent = '🌙';
  } else {
    document.body.classList.remove('dark');
    localStorage.setItem('theme', 'light');
    document.getElementById('theme-icon').textContent = '☀️';
  }
}

function toggleTheme() {
  const isDark = document.body.classList.contains('dark');
  setTheme(isDark ? 'light' : 'dark');
}

window.addEventListener('DOMContentLoaded', function() {
  const saved = localStorage.getItem('theme');
  setTheme(saved === 'dark' ? 'dark' : 'light');

  // Formatação automática de CPF/CNPJ
  const input = document.getElementById('identificador');
  if (input) {
    input.addEventListener('input', function(e) {
      let v = input.value.replace(/\D/g, '');
      if (v.length <= 11) {
        // CPF
        v = v.replace(/(\d{3})(\d)/, '$1.$2');
        v = v.replace(/(\d{3})(\d)/, '$1.$2');
        v = v.replace(/(\d{3})(\d{1,2})$/, '$1-$2');
      } else {
        // CNPJ
        v = v.replace(/(\d{2})(\d)/, '$1.$2');
        v = v.replace(/(\d{3})(\d)/, '$1.$2');
        v = v.replace(/(\d{3})(\d)/, '$1/$2');
        v = v.replace(/(\d{4})(\d{1,2})$/, '$1-$2');
      }
      input.value = v;
    });
  }

  // Loading state no botão
  const form = document.getElementById('consulta-form');
  if (form) {
    form.addEventListener('submit', function(e) {
      const btn = form.querySelector('button[type="submit"]');
      if (btn) {
        btn.classList.add('loading');
        btn.innerHTML = '<span class="loader"></span>Consultando...';
      }
    });
  }
  
  // --- Visual enhancements: mouse parallax + particles ---
  initParallaxAndParticles();
});

// Parallax card tilt and particle system
function initParallaxAndParticles() {
  const card = document.querySelector('.detective-card');
  if (card) card.classList.add('detective-card-3d','tilt');

  // Track mouse position as percentages for CSS vars
  let lastSpawn = 0;
  const spawnThrottleMs = 30; // minimum ms between particle spawns
  window.addEventListener('mousemove', (e) => {
    const x = (e.clientX / window.innerWidth) * 100;
    const y = (e.clientY / window.innerHeight) * 100;
    document.documentElement.style.setProperty('--mouse-x', x + '%');
    document.documentElement.style.setProperty('--mouse-y', y + '%');

    // tilt effect for card
    const cx = window.innerWidth / 2;
    const cy = window.innerHeight / 2;
    const dx = (e.clientX - cx) / cx; // -1 .. 1
    const dy = (e.clientY - cy) / cy;
    const rotX = (dy * 6).toFixed(2);
    const rotY = (dx * -6).toFixed(2);
    if (card) {
      card.style.transform = `rotateX(${rotX}deg) rotateY(${rotY}deg)`;
    }

    // emit particle on move (throttled)
    const now = Date.now();
    if (now - lastSpawn > spawnThrottleMs) {
      spawnParticle(e.clientX, e.clientY);
      lastSpawn = now;
    }
  });

  // Create canvas for particles
  let canvas = document.getElementById('particle-canvas');
  if (!canvas) {
    canvas = document.createElement('canvas');
    canvas.id = 'particle-canvas';
    document.body.appendChild(canvas);
  }
  const ctx = canvas.getContext('2d');
  function resize() { canvas.width = window.innerWidth; canvas.height = window.innerHeight; }
  resize();
  window.addEventListener('resize', resize);

  const particles = [];
  function spawnParticle(x, y) {
    const p = {
      x, y,
      vx: (Math.random() - 0.5) * 0.6,
      vy: (Math.random() - 0.5) * 0.6,
      size: 2 + Math.random() * 4,
      life: 40 + Math.random() * 40,
      hue: 180 + Math.random() * 80
    };
    particles.push(p);
    if (particles.length > 220) particles.splice(0, particles.length - 220);
  }

  function step() {
    ctx.clearRect(0,0,canvas.width,canvas.height);
    for (let i = particles.length -1; i >=0; i--) {
      const p = particles[i];
      p.x += p.vx;
      p.y += p.vy;
      p.vx *= 0.99;
      p.vy *= 0.99;
      p.life -= 1;
      const alpha = Math.max(0, p.life / 80);
      ctx.beginPath();
      ctx.fillStyle = `hsla(${p.hue},70%,60%,${alpha})`;
      ctx.arc(p.x, p.y, p.size * alpha, 0, Math.PI*2);
      ctx.fill();
      if (p.life <= 0) particles.splice(i,1);
    }
    requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}
