// ============================================================
// LDD · Main JavaScript
// ============================================================

document.addEventListener('DOMContentLoaded', () => {

  // ---------- NAVBAR scroll behavior ----------
  const navbar = document.getElementById('navbar');
  if (navbar) {
    window.addEventListener('scroll', () => {
      if (window.scrollY > 20) {
        navbar.classList.add('scrolled');
      } else {
        navbar.classList.remove('scrolled');
      }
    });
  }

  // ---------- Mobile hamburger menu ----------
  const hamburger = document.getElementById('hamburger');
  const mobileMenu = document.getElementById('mobileMenu');
  if (hamburger && mobileMenu) {
    hamburger.addEventListener('click', () => {
      const isOpen = mobileMenu.classList.toggle('open');
      hamburger.setAttribute('aria-expanded', isOpen);
      // Animate hamburger lines
      const spans = hamburger.querySelectorAll('span');
      if (isOpen) {
        spans[0].style.transform = 'translateY(7px) rotate(45deg)';
        spans[1].style.opacity = '0';
        spans[2].style.transform = 'translateY(-7px) rotate(-45deg)';
      } else {
        spans[0].style.transform = '';
        spans[1].style.opacity = '';
        spans[2].style.transform = '';
      }
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (!hamburger.contains(e.target) && !mobileMenu.contains(e.target)) {
        mobileMenu.classList.remove('open');
        hamburger.setAttribute('aria-expanded', false);
        hamburger.querySelectorAll('span').forEach(s => { s.style.transform = ''; s.style.opacity = ''; });
      }
    });
  }

  // ---------- Smooth scroll for anchor links ----------
  document.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener('click', (e) => {
      const target = document.querySelector(link.getAttribute('href'));
      if (target) {
        e.preventDefault();
        const offset = 80;
        const top = target.getBoundingClientRect().top + window.scrollY - offset;
        window.scrollTo({ top, behavior: 'smooth' });
        if (mobileMenu) mobileMenu.classList.remove('open');
      }
    });
  });

  // ---------- Intersection Observer for fade-in animations ----------
  const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -40px 0px'
  };

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
        observer.unobserve(entry.target);
      }
    });
  }, observerOptions);

  // Observe animatable elements
  const animatables = document.querySelectorAll(
    '.benefit-card, .channel-card, .testimonial-card, .step, .compliance-badge, .company-card, .diff-item'
  );

  animatables.forEach((el, i) => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = `opacity 0.5s ease ${i * 0.05}s, transform 0.5s ease ${i * 0.05}s`;
    observer.observe(el);
  });

  // ---------- Hero company search redirect ----------
  const heroSearch = document.getElementById('heroCompanySearch');
  if (heroSearch) {
    heroSearch.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && heroSearch.value.trim()) {
        window.location.href = `empresas.html?q=${encodeURIComponent(heroSearch.value.trim())}`;
      }
    });
  }

  // Pre-fill search on empresas page
  const companySearchInput = document.getElementById('companySearch');
  if (companySearchInput) {
    const params = new URLSearchParams(window.location.search);
    const q = params.get('q');
    if (q) {
      companySearchInput.value = q;
      companySearchInput.dispatchEvent(new Event('input'));
    }
    companySearchInput.focus();
  }

  // ---------- Stats counter animation ----------
  const statNumbers = document.querySelectorAll('.stat-number');
  const statsObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const el = entry.target;
        const text = el.textContent;
        const num = parseInt(text.replace(/\D/g, ''));
        if (num && num > 1) {
          animateCounter(el, num, text);
        }
        statsObserver.unobserve(el);
      }
    });
  }, { threshold: 0.5 });

  statNumbers.forEach(el => statsObserver.observe(el));

  function animateCounter(el, target, originalText) {
    const duration = 1200;
    const start = performance.now();
    const prefix = originalText.replace(/[\d.]+/, '');
    const suffix = originalText.match(/[^\d]+$/)?.[0] || '';

    function update(time) {
      const elapsed = time - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = Math.round(eased * target);
      el.textContent = (originalText.startsWith('+') ? '+' : '') + current + suffix.replace(/^\d+/, '');
      if (progress < 1) requestAnimationFrame(update);
      else el.textContent = originalText;
    }
    requestAnimationFrame(update);
  }

  // ---------- Active nav link on scroll ----------
  const sections = document.querySelectorAll('section[id]');
  const navAnchors = document.querySelectorAll('.nav-links a[href^="#"]');

  if (sections.length && navAnchors.length) {
    const sectionObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          navAnchors.forEach(a => a.style.color = '');
          const active = document.querySelector(`.nav-links a[href="#${entry.target.id}"]`);
          if (active) active.style.color = 'var(--red-600)';
        }
      });
    }, { rootMargin: '-30% 0px -60% 0px' });

    sections.forEach(s => sectionObserver.observe(s));
  }

});
