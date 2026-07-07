// Intercepts /members/new when navigated from within the members segment,
// rendering the standalone page (registration form, which is itself a modal)
// over the members list. Re-exporting keeps the server data-loading in one place.
export { default, metadata } from "../../new/page";
