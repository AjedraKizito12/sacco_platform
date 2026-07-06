// Intercepts the sibling /new route from within this segment, rendering the
// standalone page (a modal form) over the list. Re-exporting keeps the server
// data-loading defined in one place.
export { default, metadata } from "../../new/page";
