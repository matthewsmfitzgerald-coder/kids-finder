// The home page. It's a Server Component (the default in the App Router) that
// simply renders our interactive client component. The heavy lifting -- loading
// the JSON and filtering -- happens inside Finder, in the browser.
import Finder from "./Finder";

export default function Home() {
  return <Finder />;
}
