import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter/index.css";
import "./styles.css";
import App from "./App";

const root = document.getElementById("root");
if (!root) throw new Error("Missing application root element");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
