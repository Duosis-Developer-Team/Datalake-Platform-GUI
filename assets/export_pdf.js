/**
 * Capture a DOM element as a multi-page PDF using html2canvas + jsPDF (UMD builds from CDN).
 * Loaded by Dash from /assets/export_pdf.js
 */
(function () {
  "use strict";

  var HC_SRC = "https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js";
  var PDF_SRC = "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js";

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src;
      s.async = true;
      s.onload = function () {
        resolve();
      };
      s.onerror = function () {
        reject(new Error("Failed to load " + src));
      };
      document.head.appendChild(s);
    });
  }

  var loadPromise = null;
  function ensureLibs() {
    if (window.html2canvas && window.jspdf && window.jspdf.jsPDF) {
      return Promise.resolve();
    }
    if (loadPromise) {
      return loadPromise;
    }
    loadPromise = loadScript(HC_SRC)
      .then(function () {
        return loadScript(PDF_SRC);
      })
      .then(function () {
        if (!window.html2canvas || !window.jspdf || !window.jspdf.jsPDF) {
          throw new Error("html2canvas or jsPDF not available after load");
        }
      });
    return loadPromise;
  }

  /**
   * @param {string} elementId - Element id (without #)
   * @param {string} filename - Download filename, should end with .pdf
   */
  window.triggerPagePDF = function (elementId, filename) {
    var el = document.getElementById(elementId);
    if (!el) {
      console.error("triggerPagePDF: element not found:", elementId);
      return Promise.reject(new Error("Element not found: " + elementId));
    }
    var safeName = filename && filename.endsWith(".pdf") ? filename : (filename || "export") + ".pdf";

    return ensureLibs()
      .then(function () {
        return window.html2canvas(el, {
          scale: Math.min(2, window.devicePixelRatio || 1.5),
          useCORS: true,
          allowTaint: true,
          logging: false,
        });
      })
      .then(function (canvas) {
        var jsPDF = window.jspdf.jsPDF;
        var imgData = canvas.toDataURL("image/jpeg", 0.92);
        var pdfW = 210;
        var pdfH = 297;
        var margin = 8;
        var usableW = pdfW - 2 * margin;
        var usableH = pdfH - 2 * margin;
        var imgW = canvas.width;
        var imgH = canvas.height;
        var ratio = usableW / imgW;
        var pageImgH = imgH * ratio;
        var pdf = new jsPDF({ unit: "mm", format: "a4", orientation: "portrait" });
        var y = 0;
        var page = 0;
        while (y < imgH - 1) {
          if (page > 0) {
            pdf.addPage();
          }
          var slicePx = Math.min(imgH - y, usableH / ratio);
          var sliceCanvas = document.createElement("canvas");
          sliceCanvas.width = imgW;
          sliceCanvas.height = Math.ceil(slicePx);
          var ctx = sliceCanvas.getContext("2d");
          ctx.drawImage(canvas, 0, y, imgW, slicePx, 0, 0, imgW, slicePx);
          var sliceData = sliceCanvas.toDataURL("image/jpeg", 0.92);
          var sliceMmH = slicePx * ratio;
          pdf.addImage(sliceData, "JPEG", margin, margin, usableW, sliceMmH);
          y += slicePx;
          page += 1;
        }
        pdf.save(safeName);
      })
      .catch(function (err) {
        console.error("triggerPagePDF failed:", err);
        throw err;
      });
  };
})();
