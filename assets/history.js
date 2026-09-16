"use strict";
const selector = document.getElementById("cohort");
const pages = Array.from(document.querySelectorAll(".cohort"));

function selectCohort() {
  for (const page of pages) {
    page.hidden = page.dataset.cohort !== selector.value;
  }
}

function revealRecord() {
  const target = document.getElementById(location.hash.slice(1));
  if (!target || target.tagName !== "DETAILS") return;
  const page = target.closest(".cohort");
  selector.value = page.dataset.cohort;
  selectCohort();
  target.open = true;
  target.scrollIntoView({ block: "start" });
}

selector.addEventListener("change", selectCohort);
document.addEventListener("click", event => {
  const link = event.target.closest('a[href^="#record-"]');
  if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  if (location.hash !== link.hash) history.pushState(null, "", link.hash);
  revealRecord();
});
window.addEventListener("hashchange", revealRecord);
window.addEventListener("popstate", revealRecord);
selectCohort();
revealRecord();
