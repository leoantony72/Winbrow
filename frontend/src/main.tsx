import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import DynamicIslandDemo from "./demos/dynamic-island-demo";
import "./styles.css";
import "./workspace.css";

const componentDemo =
  new URLSearchParams(location.search).get("win") === "component-demo";
const container = document.getElementById("root");
if (container) {
  createRoot(container).render(
    <React.StrictMode>
      {componentDemo ? <DynamicIslandDemo /> : <App />}
    </React.StrictMode>,
  );
}
