const path = require('path');

module.exports = {
    entry: './src/lib/index.js',
    output: {
        path: path.resolve(__dirname, 'dash_globe_component'),
        filename: 'dash_globe_component.min.js',
        library: 'dash_globe_component',
        libraryTarget: 'window',
    },
    resolve: {
        extensions: ['.js', '.jsx'],
    },
    module: {
        rules: [
            {
                test: /\.jsx?$/,
                exclude: /node_modules/,
                use: {
                    loader: 'babel-loader',
                    options: {
                        presets: ['@babel/preset-env', '@babel/preset-react'],
                    },
                },
            },
        ],
    },
    externals: {
        react: 'React',
        'react-dom': 'ReactDOM',
    },
    mode: 'production',
};
