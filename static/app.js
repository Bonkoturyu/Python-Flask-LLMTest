"use strict";

const form = document.getElementById("question-form");
const submitButton = document.getElementById("submit-button");

form?.addEventListener("submit", () => {
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.textContent = "送信中…";
  }
});
