const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// 画面の下のおじいちゃんとおばあちゃん: 画面の下が見えたら中尊寺まで歩き、さわると1回はねる
document.querySelectorAll(".footer-dog").forEach((dog) => {
  dog.addEventListener("click", () => {
    dog.classList.remove("hop");
    void dog.offsetWidth;
    dog.classList.add("hop");
  });

  const footer = dog.closest(".dog-footer");
  const temple = footer?.querySelector("[data-chusonji]");
  if (!footer || !temple) return;

  const SPEED = 26;
  let started = false;

  const targetLeft = () => {
    const t = temple.getBoundingClientRect();
    const f = footer.getBoundingClientRect();
    const center = t.left + t.width / 2 - f.left + 40;
    return Math.max(4, Math.min(center - dog.offsetWidth / 2, f.width - dog.offsetWidth - 6));
  };

  const arrive = () => {
    dog.classList.remove("walking");
    dog.classList.add("arrived");
  };

  const start = () => {
    if (started) return;
    started = true;
    const to = targetLeft();
    if (reduceMotion) {
      dog.style.transitionDuration = "0s";
      dog.style.left = `${to}px`;
      arrive();
      return;
    }
    const distance = dog.offsetLeft - to;
    if (distance <= 0) {
      arrive();
      return;
    }
    dog.style.transitionDuration = `${distance / SPEED}s`;
    dog.classList.add("walking");
    dog.style.left = `${to}px`;
  };

  dog.addEventListener("transitionend", (e) => {
    if (e.propertyName === "left") arrive();
  });

  new IntersectionObserver((entries, observer) => {
    if (entries.some((entry) => entry.isIntersecting)) {
      observer.disconnect();
      setTimeout(start, 400);
    }
  }, { threshold: 0.6 }).observe(footer);

  window.addEventListener("resize", () => {
    if (!dog.classList.contains("arrived")) return;
    dog.style.transitionDuration = "0s";
    dog.style.left = `${targetLeft()}px`;
  });
});

// 画面の下の景色: 東北本線の電車とコミュニティバスがときどき通る
const scenery = document.querySelector(".scenery");

if (scenery && !reduceMotion) {
  const VIEW_W = 1200;
  const VIEW_H = 112;

  const visibleRange = () => {
    const r = scenery.getBoundingClientRect();
    const scale = Math.max(r.width / VIEW_W, r.height / VIEW_H);
    const half = r.width / scale / 2;
    return [VIEW_W / 2 - half, VIEW_W / 2 + half];
  };

  const drive = (el, { direction, speed, firstDelay, gap }) => {
    if (!el) return;
    const run = () => {
      const [left, right] = visibleRange();
      const length = el.getBBox().width;
      const start = direction < 0 ? right + 10 : left - length - 10;
      const end = direction < 0 ? left - length - 10 : right + 10;
      const animation = el.animate(
        [{ transform: `translateX(${start}px)` }, { transform: `translateX(${end}px)` }],
        { duration: (Math.abs(end - start) / speed) * 1000, easing: "linear", fill: "both" },
      );
      animation.finished.then(() => setTimeout(run, gap[0] + Math.random() * (gap[1] - gap[0])));
    };
    setTimeout(run, firstDelay);
  };

  drive(scenery.querySelector("#train"), { direction: -1, speed: 70, firstDelay: 1500, gap: [5000, 11000] });
  drive(scenery.querySelector("#bus"), { direction: 1, speed: 30, firstDelay: 3500, gap: [4000, 9000] });
}

// おでかけの道のり: おじいちゃんとおばあちゃんが家から行き先まで歩く
const journey = document.querySelector("[data-journey]");

if (journey) {
  const walker = journey.querySelector(".walker");
  const bubble = walker.querySelector(".bubble");
  const steps = [...journey.querySelectorAll(".journey-step")];
  const replay = document.querySelector("[data-replay]");
  let running = false;

  const positionOf = (step) => step.offsetLeft;

  const moveTo = (index) => {
    walker.style.transform = `translateX(${positionOf(steps[index])}px)`;
    walker.classList.toggle("edge-left", index === 0);
    walker.classList.toggle("edge-right", index === steps.length - 1);
  };

  const say = (text) => {
    bubble.hidden = false;
    bubble.textContent = text;
    bubble.style.animation = "none";
    void bubble.offsetWidth;
    bubble.style.animation = "";
  };

  const reset = () => {
    walker.style.transition = "none";
    walker.classList.remove("walking", "arrived");
    steps.forEach((s) => s.classList.remove("reached"));
    bubble.hidden = true;
    moveTo(0);
    void walker.offsetWidth;
    walker.style.transition = "";
  };

  const showArrived = () => {
    walker.style.transition = "none";
    moveTo(steps.length - 1);
    walker.classList.add("arrived");
    steps.forEach((s) => s.classList.add("reached"));
    say(journey.dataset.arrive);
  };

  const walk = async () => {
    if (running) return;
    running = true;
    reset();
    steps[0].classList.add("reached");
    say(journey.dataset.depart);
    await wait(1800);
    bubble.hidden = true;
    walker.classList.add("walking");
    for (let i = 1; i < steps.length; i += 1) {
      moveTo(i);
      await wait(1300);
      steps[i].classList.add("reached");
    }
    walker.classList.remove("walking");
    walker.classList.add("arrived");
    say(journey.dataset.arrive);
    running = false;
  };

  if (reduceMotion) {
    showArrived();
  } else {
    reset();
    setTimeout(walk, 600);
  }

  replay?.addEventListener("click", () => (reduceMotion ? showArrived() : walk()));
  walker.addEventListener("click", () => (reduceMotion ? showArrived() : walk()));

  window.addEventListener("resize", () => {
    if (!running) moveTo(walker.classList.contains("arrived") || reduceMotion ? steps.length - 1 : 0);
  });
}
