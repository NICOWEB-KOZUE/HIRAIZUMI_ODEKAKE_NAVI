const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// 画面の下の犬: さわると1回はねる
document.querySelectorAll(".footer-dog").forEach((dog) => {
  dog.addEventListener("click", () => {
    dog.classList.remove("hop");
    void dog.offsetWidth;
    dog.classList.add("hop");
  });
});

// 「それ以外の日」を選んだら日付の入力欄を出す
document.querySelectorAll("input[name='date']").forEach((radio) => {
  radio.addEventListener("change", () => {
    const otherRadio = document.querySelector("[data-other-date]");
    const input = document.querySelector(".date-input");
    if (!otherRadio || !input) return;
    input.hidden = !otherRadio.checked;
    input.required = otherRadio.checked;
    if (otherRadio.checked) input.focus();
  });
});

// おでかけの道のり: 犬が家から行き先まで歩く
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
