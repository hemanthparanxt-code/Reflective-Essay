/*
Aurora Reflective Essay evaluator — paste into DevTools Console on the
Faculty Portal's Evaluate page. Start the Python backend first.

Safety: DRY_RUN defaults to true. Inspect results, then set false only after
testing the PDF download, question matching, and points field on one student.
The script stops if it cannot safely identify the PDF or the points input.
*/
(async function () {
  const CONFIG = {
    BACKEND: "http://127.0.0.1:8765/evaluate",
    DRY_RUN: true,             // change to false after a successful test
    AUTO_SAVE_NEXT: false,     // enable only after validating one-student test
    NEXT_TIMEOUT: 12000,
    POLL_MS: 200,
    MAX_STUDENTS_PER_RUN: 73
  };
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  function getStudentInfo() {
    const match = document.body.innerText.match(/Student\s+(\d+)\s+of\s+(\d+)/i);
    return match ? { current: Number(match[1]), total: Number(match[2]) } : null;
  }

  function findSubmittedPdfLink() {
    const anchors = [...document.querySelectorAll("a[href]")];
    // Prefer a PDF link in/near the Submitted Work section.
    const submittedHeading = [...document.querySelectorAll("h1,h2,h3,h4,div,p,span")]
      .find(el => el.children.length < 3 && /submitted work/i.test((el.innerText || "").trim()));
    if (submittedHeading) {
      let node = submittedHeading;
      for (let depth = 0; node && depth < 6; depth++, node = node.parentElement) {
        const local = [...node.querySelectorAll("a[href]")].find(a =>
          /\.pdf(?:$|[?#])/i.test(a.href) || /open/i.test(a.innerText || "")
        );
        if (local) return local;
      }
    }
    return anchors.find(a => /\.pdf(?:$|[?#])/i.test(a.href)) ||
           anchors.find(a => /open/i.test(a.innerText || "") && a.href);
  }

  async function fetchSubmissionPdf() {
    const link = findSubmittedPdfLink();
    if (!link) throw new Error("Could not find the submitted PDF link. No marks were changed.");
    const response = await fetch(link.href, { credentials: "include" });
    if (!response.ok) throw new Error(`PDF download failed: HTTP ${response.status}.`);
    const blob = await response.blob();
    if (blob.size < 100 || (blob.type && !/pdf/i.test(blob.type))) {
      // Some portals return application/octet-stream for valid PDFs; validate header too.
      const bytes = new Uint8Array(await blob.slice(0, 5).arrayBuffer());
      const signature = String.fromCharCode(...bytes);
      if (signature !== "%PDF-") throw new Error("The portal link did not return a readable PDF.");
    }
    return { blob, filename: (link.href.split("/").pop() || "submission.pdf").split("?")[0] };
  }

  async function evaluatePdf() {
    const { blob, filename } = await fetchSubmissionPdf();
    const form = new FormData();
    form.append("file", blob, filename.toLowerCase().endsWith(".pdf") ? filename : "submission.pdf");
    const response = await fetch(CONFIG.BACKEND, { method: "POST", body: form });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Evaluator returned HTTP ${response.status}`);
    if (!Number.isInteger(data.total) || data.total < 0 || data.total > 200) {
      throw new Error("Evaluator returned an invalid total.");
    }
    if (!Array.isArray(data.questions) || data.questions.length !== 5) {
      throw new Error("Evaluator did not return five question scores.");
    }
    const sum = data.questions.reduce((n, q) => n + Number(q.score), 0);
    if (sum !== data.total) throw new Error(`Score mismatch: question sum ${sum}, total ${data.total}.`);
    return data;
  }

  function findPointsInput() {
    const candidates = [...document.querySelectorAll("input:not([type=hidden]), textarea")]
      .filter(el => {
        const labelText = [
          el.getAttribute("placeholder"), el.getAttribute("aria-label"),
          el.name, el.id, el.parentElement?.innerText
        ].filter(Boolean).join(" ");
        return /points|out of 200/i.test(labelText) &&
          !/search|filter/i.test(labelText);
      });
    if (candidates.length === 1) return candidates[0];

    // Screenshot layout may have a plain numeric input whose nearby label says "Points (out of 200)".
    const fallback = [...document.querySelectorAll("input[type=number],input:not([type=hidden])")]
      .filter(el => {
        const p = el.parentElement?.parentElement?.innerText || "";
        return /points\s*\(out of 200\)/i.test(p);
      });
    return fallback.length === 1 ? fallback[0] : null;
  }

  function setNativeInputValue(el, value) {
    const setter = Object.getOwnPropertyDescriptor(
      el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype,
      "value"
    )?.set;
    if (!setter) throw new Error("Could not set the Points field safely.");
    setter.call(el, String(value));
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
  }

  function getSaveNextButton() {
    return [...document.querySelectorAll("button")].find(button =>
      (button.innerText || "").replace(/\s+/g, " ").trim().toLowerCase().startsWith("save & next")
    );
  }

  async function waitForNext(previous) {
    const start = Date.now();
    while (Date.now() - start < CONFIG.NEXT_TIMEOUT) {
      await sleep(CONFIG.POLL_MS);
      const info = getStudentInfo();
      if (info && info.current !== previous) return info;
    }
    return null;
  }

  const results = [];
  console.log("Reflective Essay Evaluator started.", CONFIG);
  console.log("Backend health check: http://127.0.0.1:8765/health");

  for (let count = 0; count < CONFIG.MAX_STUDENTS_PER_RUN; count++) {
    const student = getStudentInfo();
    if (!student) { console.error("Student counter not found; stopping."); break; }

    const pageText = document.body.innerText;
    const hasSubmission = /submitted work/i.test(pageText) &&
      !!findSubmittedPdfLink();

    if (!hasSubmission) {
      const result = { student: student.current, total: student.total, submitted: false, score: 0,
        note: "No submitted PDF link detected; verify portal status manually." };
      results.push(result);
      console.warn(result);
      if (CONFIG.DRY_RUN) {
        console.log("DRY RUN: no score entered or saved.");
      } else {
        const input = findPointsInput();
        if (!input) { console.error("Points input not uniquely identified. Stopping."); break; }
        setNativeInputValue(input, 0);
      }
    } else {
      let evaluation;
      try {
        evaluation = await evaluatePdf();
      } catch (error) {
        console.error(`Student ${student.current}: evaluation failed. Stopping without saving.`, error);
        break;
      }

      const result = {
        student: student.current, total: student.total, submitted: true,
        score: evaluation.total,
        questionScores: evaluation.questions.map(q => q.score),
        overallFeedback: evaluation.overall_feedback,
        needsHumanReview: !!evaluation.needs_human_review,
        reviewReason: evaluation.review_reason || ""
      };
      results.push(result);
      console.group(`Student ${student.current}/${student.total} — ${evaluation.total}/200`);
      console.table(evaluation.questions.map(q => ({
        question: q.number, score: `${q.score}/40`, relevance: q.relevance,
        correctness: q.correctness, feedback: q.feedback
      })));
      console.log("Overall feedback:", evaluation.overall_feedback);
      console.log("Human review required:", evaluation.needs_human_review, evaluation.review_reason || "");
      console.groupEnd();

      if (evaluation.needs_human_review) {
        console.warn("Review flag is set. Inspect this student's work before saving.");
        if (!CONFIG.DRY_RUN) {
          console.error("Stopping before saving because human review is required.");
          break;
        }
      }

      if (CONFIG.DRY_RUN) {
        console.log(`DRY RUN: would enter ${evaluation.total}/200 for student ${student.current}.`);
      } else {
        const input = findPointsInput();
        if (!input) { console.error("Points input not uniquely identified. Stopping."); break; }
        setNativeInputValue(input, evaluation.total);
        await sleep(300);
        const currentValue = Number(input.value);
        if (currentValue !== evaluation.total) {
          console.error("Points field verification failed; stopping without Save & Next.");
          break;
        }
      }
    }

    if (!CONFIG.AUTO_SAVE_NEXT || CONFIG.DRY_RUN) {
      console.log("Stopped before Save & Next (safe mode). Set AUTO_SAVE_NEXT=true only after testing.");
      break;
    }

    const saveNext = getSaveNextButton();
    if (!saveNext) { console.error("Save & Next button not found; stopping."); break; }
    saveNext.click();

    if (student.current >= student.total) {
      console.log("Reached final student.");
      break;
    }
    const next = await waitForNext(student.current);
    if (!next) { console.error("Next student did not load; stopping."); break; }
    console.log(`Loaded student ${next.current}/${next.total}`);
  }

  window.reflectiveEssayEvaluationResults = results;
  console.log("Evaluation run summary:");
  console.table(results.map(r => ({
    student: r.student, submitted: r.submitted, score: r.score,
    needsHumanReview: r.needsHumanReview || false
  })));
  console.log("Full results: window.reflectiveEssayEvaluationResults");
})();
