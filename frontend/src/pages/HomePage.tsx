// const HomePage = () => {
//   return <h1 className="text-3xl font-bold">Welcome to UniRover</h1>;
// };
// export default HomePage;

const HomePage = () => {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <main className="flex-grow">
        <section className="max-w-7xl mx-auto px-8 py-20 text-center">
          <h2 className="text-5xl font-extrabold text-gray-900 mb-6">
            Smart Indoor Delivery with ROSbot
          </h2>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto mb-8">
            UniRover revolutionizes indoor logistics with autonomous, efficient, and reliable delivery powered by ROSbot technology.
          </p>
        </section>

        <section id="features" className="bg-white py-20">
          <div className="max-w-7xl mx-auto px-8">
            <h3 className="text-3xl font-bold text-gray-900 mb-12 text-center">Why UniRover?</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              <div className="text-center">
                <div className="text-4xl mb-4">🤖</div>
                <h4 className="text-xl font-semibold text-gray-900 mb-2">Autonomous Navigation</h4>
                <p className="text-gray-600">Seamlessly navigates complex indoor spaces using advanced ROSbot algorithms.</p>
              </div>
              <div className="text-center">
                <div className="text-4xl mb-4">⚡</div>
                <h4 className="text-xl font-semibold text-gray-900 mb-2">Efficient Delivery</h4>
                <p className="text-gray-600">Optimizes routes to ensure fast and reliable package delivery.</p>
              </div>
              <div className="text-center">
                <div className="text-4xl mb-4">🔒</div>
                <h4 className="text-xl font-semibold text-gray-900 mb-2">Secure & Safe</h4>
                <p className="text-gray-600">Built-in safety protocols protect both goods and environments.</p>
              </div>
            </div>
          </div>
        </section>

        <section id="about" className="py-20">
          <div className="max-w-7xl mx-auto px-8 text-center">
            <h3 className="text-3xl font-bold text-gray-900 mb-6">About UniRover</h3>
            <p className="text-lg text-gray-600 max-w-3xl mx-auto">
              UniRover leverages cutting-edge ROSbot technology to provide a scalable, autonomous indoor delivery system. Designed for offices, hospitals, and campuses, it simplifies logistics while enhancing efficiency.
            </p>
          </div>
        </section>
      </main>

      <footer id="contact" className="bg-gray-900 text-white py-8">
        <div className="max-w-7xl mx-auto px-8 text-center">
          <p className="text-lg mb-4">Ready to transform your indoor logistics?</p>
          <a href="mailto:info@unirover.com" className="text-gray-300 hover:text-white">info@unirover.com</a>
          <p className="mt-4 text-sm text-gray-400">© 2025 UniRover. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
};

export default HomePage;