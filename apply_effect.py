#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re

files = [
    'templates/modern-form.html',
    'templates/modern-result.html',
    'templates/view-resultado.html',
    'templates/admin_dashboard.html',
    'templates/admin_logs.html',
    'templates/historico.html',
    'templates/login.html',
    'templates/mudar-senha-obrigatoria.html',
    'templates/usuarios.html'
]

new_code = """// Cyber Constellation Effect
    const canvas = document.getElementById('detective-canvas');
    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    
    let mouseX = canvas.width / 2;
    let mouseY = canvas.height / 2;
    let time = 0;
    
    class Node {
      constructor() {
        this.x = Math.random() * canvas.width;
        this.y = Math.random() * canvas.height;
        this.vx = (Math.random() - 0.5) * 0.3;
        this.vy = (Math.random() - 0.5) * 0.3;
        this.radius = Math.random() * 2 + 1;
        this.pulseOffset = Math.random() * Math.PI * 2;
      }
      update() {
        this.x += this.vx;
        this.y += this.vy;
        if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
        if (this.y < 0 || this.y > canvas.height) this.vy *= -1;
        const dx = mouseX - this.x;
        const dy = mouseY - this.y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        if (distance < 150) {
          const force = (150 - distance) / 150;
          this.x -= (dx / distance) * force * 2;
          this.y -= (dy / distance) * force * 2;
        }
      }
      draw() {
        const pulse = Math.sin(time * 0.002 + this.pulseOffset) * 0.5 + 0.5;
        const glowSize = this.radius + pulse * 2;
        const gradient = ctx.createRadialGradient(this.x, this.y, 0, this.x, this.y, glowSize * 3);
        gradient.addColorStop(0, `rgba(139, 92, 246, ${0.6 * pulse})`);
        gradient.addColorStop(0.5, `rgba(59, 130, 246, ${0.3 * pulse})`);
        gradient.addColorStop(1, 'rgba(59, 130, 246, 0)');
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(this.x, this.y, glowSize * 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = `rgba(255, 255, 255, ${0.8 + pulse * 0.2})`;
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    class Particle {
      constructor() {
        this.x = Math.random() * canvas.width;
        this.y = Math.random() * canvas.height;
        this.size = Math.random() * 1.5 + 0.5;
        this.speedX = (Math.random() - 0.5) * 0.5;
        this.speedY = (Math.random() - 0.5) * 0.5;
        this.opacity = Math.random() * 0.5 + 0.2;
      }
      update() {
        this.x += this.speedX;
        this.y += this.speedY;
        if (this.x < 0) this.x = canvas.width;
        if (this.x > canvas.width) this.x = 0;
        if (this.y < 0) this.y = canvas.height;
        if (this.y > canvas.height) this.y = 0;
      }
      draw() {
        ctx.fillStyle = `rgba(147, 197, 253, ${this.opacity})`;
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    const nodes = [];
    const particles = [];
    for (let i = 0; i < 40; i++) nodes.push(new Node());
    for (let i = 0; i < 60; i++) particles.push(new Particle());
    function drawConnections() {
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const distance = Math.sqrt(dx * dx + dy * dy);
          if (distance < 150) {
            const opacity = (1 - distance / 150) * 0.3;
            ctx.strokeStyle = `rgba(139, 92, 246, ${opacity})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.stroke();
          }
        }
      }
    }
    function animate() {
      time++;
      const gradient = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
      const hue1 = (time * 0.05) % 360;
      const hue2 = (hue1 + 60) % 360;
      gradient.addColorStop(0, `hsla(${hue1}, 70%, 8%, 0.95)`);
      gradient.addColorStop(0.5, 'hsla(240, 60%, 5%, 0.95)');
      gradient.addColorStop(1, `hsla(${hue2}, 70%, 8%, 0.95)`);
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      particles.forEach(p => {
        p.update();
        p.draw();
      });
      drawConnections();
      nodes.forEach(node => {
        node.update();
        node.draw();
      });
      const cursorGlow = ctx.createRadialGradient(mouseX, mouseY, 0, mouseX, mouseY, 80);
      cursorGlow.addColorStop(0, 'rgba(139, 92, 246, 0.15)');
      cursorGlow.addColorStop(0.5, 'rgba(59, 130, 246, 0.08)');
      cursorGlow.addColorStop(1, 'rgba(59, 130, 246, 0)');
      ctx.fillStyle = cursorGlow;
      ctx.beginPath();
      ctx.arc(mouseX, mouseY, 80, 0, Math.PI * 2);
      ctx.fill();
      requestAnimationFrame(animate);
    }
    animate();
    document.addEventListener('mousemove', (e) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
    });
    window.addEventListener('resize', () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    });"""

base_path = 'c:\\Users\\giga\\Desktop\\detetive-main\\'

for file in files:
    filepath = base_path + file
    print(f"Processing {filepath}...")
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Pattern para encontrar e substituir o script inteiro
        pattern = r'<script>\s*//\s*(?:Canvas Background|Cyber Constellation|Canvas animation).*?window\.addEventListener\(\'resize\'.*?\}\);'
        
        updated = re.sub(pattern, f'<script>\n    {new_code}', content, flags=re.DOTALL)
        
        if updated != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(updated)
            print(f"✓ {filepath} atualizado com sucesso!")
        else:
            print(f"✗ Nenhuma alteração encontrada em {filepath}")
            
    except Exception as e:
        print(f"Erro ao processar {filepath}: {e}")

print("\nProcesso concluído!")
