const path = require('path');

module.exports = {
    entry: './src/lib/index.js',
    output: {
        path: path.resolve(__dirname, 'dash_hmdl_flow'),
        filename: 'dash_hmdl_flow.min.js',
        library: 'dash_hmdl_flow',
        libraryTarget: 'window',
    },
    resolve: {
        extensions: ['.js', '.jsx'],
    },
    module: {
        rules: [
            {
                test: /\.jsx?$/,
                exclude: /node_modules\/(?!@xyflow)/,
                use: {
                    loader: 'babel-loader',
                    options: {
                        presets: ['@babel/preset-env', '@babel/preset-react'],
                    },
                },
            },
            {
                test: /\.css$/,
                use: ['style-loader', 'css-loader'],
            },
        ],
    },
    externals: {
        react: 'React',
        'react-dom': 'ReactDOM',
    },
    mode: 'production',
};
