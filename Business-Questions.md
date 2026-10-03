Companies and development teams have many concerns when they try to follow trends, to be on the market, and to provide useful products/services at the same time; there are also concerns related to being profitable, being advertised, and establishing partnerships, etc.. When you build an app you may also have the same concerns if you want to flourish on the market. These concerns can be transformed into \**questions* and then the information/knowledge, obtained with the analytics engine, can support the decisions to solve those questions. We have identified 5 types of questions that encompass these concerns:

1. **Type1 - App's telemetry**: questions that are related to crashes, bugs, performance, stability issues, device-related statistics, etc.
2. **Type 2 - Direct user experience improvement**: questions that focus on improving user experience in the daily usage/interaction.
3. **Type 3 - Features analysis**: questions that helps the business to decide about the implementation of a new feature, or removal/update of an existing one.
4. **Type 4 - Benefits from data**: questions that helps the business to understand how they can make profit or take advantage from its data with third party companies.
5. **Type**\*: questions that are meant to answer more than one topic from the other four types.

Those were the main ideas behind each type of questions; we are going to explain them in more detail in the following paragraphs.

### Type 1 - App's telemetry

This type of questions is related to crashes, bugs, performance, stability issues, etc. In other words, the answers to these type of questions help you to monitor the resources of the app and how well it is performing. The data source needed to answer these questions is internal, which means no outsider data is needed. Additionally, the output/information is normally not presented to the user because telemetry data is a concern of the development team. Here are some examples:

* Is the average time of loading the app greater than our goal (1ms)?\
  If yes then we are accomplishing our goal; otherwise we wave to do something to change this behavior because it impacts the app quality as perceived by users
* What is the app code where the app constantly crashes?\
  At the main view
* What is the distribution of Android devices where our app is installed?\
  Android Oreo (50%), Lollipop (20%)....

### Type 2 - Direct user experience improvement

This type of questions is focused on improving the user experience in the daily usage/interaction. In other words, the answers to these questions are used by the user in daily interactions, therefore, the information extracted is presented directly to the user (in some way) in the app/device. The data source can be external or internal. For instance :

* Do the environmental sensors measure a good\[^1] air quality for cycling on 7th avenue?\
  Yes, then we can recommend this route for cycling today for the users that are near 7 avenue
* How many days have passed since the last symptoms reports by the user?\
  3 days, it is a reasonable time to remember the user to do it

**Note**, that this type of question can be formulated like if you are answering the question for a single user, this is because this type of questions can be related to the information of a particular user and theirs context, like our first example where the particular context is the location, near 7th avenue.

### Type 3 - Features analysis

This type of questions helps the business to decide about the implementation of a new feature or removal/update of an existing one. In other words, the answer to these questions are used as a basis to give up a functionality, that is not being accepted by the users, or to add a new functionality, or to change the UI to improve UX/UI. The data source can be internal and external. The output/information is presented to the user as the addition or removal/update of a functionality. Some examples:

* Which core functionality(ies) are being used in average less than 3 times in a week?\
  Give more information about a topic, then we can consider to remove this functionality
* In the actual market, which are the popular functionalities offered by our competition?\
  Contract tracing

### Type 4 - Benefits from data

This type of questions help the business to understand how they can make profit or take advantage from its data with third party companies. In other words, the user does not get a benefit directly; the main goal is to obtain benefit (e.g., profit, renown, etc..) from the user's data and other third-party companies. The source of data is internal, but when answering this type of questions, it can be influenced by external sources such as trends in the market. For example:

* We are a business that collects geographical data about mobilization and nationality from people. What are the geographical locations where many tourists converge on a given time?\
  Those locations are X,Y, and Z, then we can sell this information to a tourism company that sells city tours

### Type\*

This type of questions is meant to answer more than one topic from the other four types. Because of their mix nature, the data source can be internal and external, influenced by internal laws or external influences. The answers to these questions can be presented directly to the users, to third parties or both. Here is an example:

* Our revenue comes from advertisement, do the users have a particular point on the app that stays longer?\
  Yes, then we can place an add/brand that pays more at this point of the app. With this information, we can charge more for the preferential points/places and because the adds are personalized, then we are improving user experience

## Aspects to consider when formulating questions

> (Be very careful with this!)

1. Your questions cannot have subjective attributes like (good, colorful, average, enough, etc..). These types of attributes cannot be measured. An analytics engine cannot understand them, therefore you cannot answer the questions with the engine unless subjectiveness is codified in some way. If you use any of this type of attributes, like in our cycling example, then you should provide a scale to measure this attribute. Check \[^1].
2. Your questions cannot be ones that ask about possibility like: "Can we explain the traffic?". These types of questions are impossible to answer by an analytics engine.
3. With the last two types of questions you have to be very careful with the user's privacy and always consider ethical implications of your app. This is important because all the data that is related to a user's profile is personal data and may be sensible data as well, meaning that nobody is enabled to see this data, and sharing it could be a legal problem.
4. If you share users' data, you must always inform your users in the terms & conditions of your application and use a click-wrap or web-wrap agreements.
5. You may notice that in our examples we have some questions in which the answer is a simple **YES or NO**; these questions are only valid if you are validating a hypothesis, otherwise these types of questions are useless and you have to paraphrase your questions. A specific example is the following:

* Do the environmental sensors measure a good \[^1] air quality for cycling on 7th avenue? yes, **then we can recommend this route for cycling today for the users that are near 7th avenue**

Here as you can read, we gave a **context** in the answer, this context is a hypothesis. You can present this context in two ways, when you give an answer example (like the aforementioned one) or when you formulate the questions, for example: "**For the user near 7th avenue**, does 7th avenue have the necessary\[^1] environmental conditions **for being recommended as a suitable route for cycling**?".

What would happen if we take the context out of the question? , the question would look like this, ***Do the environmental sensors measure a good\[^1] air quality for cycling on 7 avenue?***, what would be the possible answers? **yes or no**, ok, now what can you do with a yes or a no?..., we guess that your answer is going to be "nothing", that is why **yes/no questions without a context are useless**. Ok, what can you do with this question? well, you can **paraphrase** it like this:

* Which sensors in 7 avenue measure a good\[^1] air quality for cycling on 7?

As you can see, the possible answers to this question are specific environmental sensors across 7th avenue (e.g., sensor 1-Hippies park and sensor 2-National park). With this answer you can conduct multiple analyses, like environmental across some paths, recommending routes, optimizing previous routes, build historic data and use them to make predictions.

> Would you like to learn more about how to formulate business questions? OK, check the next section and learn about the "data twin" technique.

\[ˆ1] A favorable value for PM-2,5 is between 0 and 10 (RMCAB Bogotá)
